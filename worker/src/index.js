/**
 * fin-assist-bot — Cloudflare Worker
 *
 * Receives Telegram webhook updates and routes them:
 *   /holdings  → triggers bot_analyse.yml  — event-driven holdings check with full status
 *   /discover  → triggers bot_scan.yml     — dynamic prospect discovery from Reddit/news/trending
 *   /digest    → triggers bot_digest.yml   — weekly digest
 *   /snapshot  → triggers bot_snapshot.yml — Notion Investments Context refresh
 *   (legacy /analyse + /scan still route to the same workflows as aliases)
 *   free text  → fetches Notion context, calls Claude API, replies inline
 *
 * Required secrets (set via `wrangler secret put`):
 *   TELEGRAM_BOT_TOKEN  — bot token from @BotFather
 *   TELEGRAM_CHAT_ID    — your personal chat ID (security filter)
 *   GH_PAT              — GitHub PAT with actions:write scope
 *   NOTION_API_KEY      — Notion integration token
 *   CLAUDE_API_KEY      — Anthropic API key
 *   SUPABASE_URL        — Supabase project URL (Phase 18: spending queries)
 *   SUPABASE_ANON_KEY   — Supabase anon key (Phase 18: spending queries)
 *
 * Env var (set in wrangler.toml [vars]):
 *   GH_REPO             — "owner/repo" e.g. "vadymuxd/fin-assist"
 */

// ---------------------------------------------------------------------------
// Command → workflow mapping
// ---------------------------------------------------------------------------

const COMMANDS = {
  '/holdings': { workflow: 'bot_analyse.yml',      label: 'Holdings check'     },
  '/discover': { workflow: 'bot_scan.yml',         label: 'Prospect discovery' },
  '/digest':   { workflow: 'bot_digest.yml',       label: 'Weekly digest'      },
  '/snapshot': { workflow: 'bot_snapshot.yml',     label: 'Investments Context refresh' },
  '/mortgage': { workflow: 'mortgage_monitor.yml', label: 'Mortgage monitor'   },
  '/sync':     { workflow: 'bot_sync.yml',         label: 'Sync snapshots'    },
  // Legacy aliases — keep old commands working
  '/analyse':  { workflow: 'bot_analyse.yml',      label: 'Holdings check'     },
  '/scan':     { workflow: 'bot_scan.yml',         label: 'Prospect discovery' },
};

// Notion page IDs for context
const NOTION_AGENT_CONFIG_ID         = '33f416f2-7566-811a-a994-e1a3561adac7';
const NOTION_MEMORY_INDEX_ID         = '33f416f2-7566-812a-8b25-fea944567cab';
const NOTION_INVESTMENTS_CONTEXT_ID  = '33f416f2-7566-81ce-b7e8-dd7b68101342';
const NOTION_USER_PROFILE_ID         = '33f416f2-7566-81f4-b5f7-dc7bbfb7e626';
const NOTION_SHEET_STRUCTURE_ID      = '33f416f2-7566-81b0-82c3-cfddebca3d9f';
const NOTION_SAVINGS_CONTEXT_ID      = '34d416f2-7566-81b6-b236-de36e284f4b1';
const NOTION_PENSIONS_CONTEXT_ID     = '34f416f2-7566-8144-8054-e371f2d6e569';
const NOTION_FINANCE_ACCOUNTS_ID     = '35b416f2-7566-81ed-a062-cf44a590ffdc';

// Phase 16 — Financial Updates DB (Claude writes NL updates here)
const NOTION_FINANCIAL_UPDATES_DB_ID = 'a863ed07-0e62-4419-b8a2-e2c0dc17c596';

// Phase 18 — spending keywords that trigger a monzo_transactions Supabase query
const SPENDING_KEYWORDS = [
  'spend', 'spending', 'spent', 'transaction', 'monzo',
  'groceries', 'eating out', 'how much did i', 'what did i',
  'last week', 'this week', 'this month', 'last month', 'today',
  'yesterday', 'recent purchases', 'recent transactions',
];

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export default {
  async fetch(request, env, ctx) {
    if (request.method !== 'POST') {
      return new Response('OK', { status: 200 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response('OK');
    }

    // Return 200 immediately; process in background so Telegram doesn't retry
    ctx.waitUntil(handleUpdate(update, env));
    return new Response('OK');
  },
};

// ---------------------------------------------------------------------------
// Update handler
// ---------------------------------------------------------------------------

async function handleUpdate(update, env) {
  const message = update.message || update.edited_message;
  if (!message?.text) return;

  const chatId = String(message.chat.id);
  const text   = message.text.trim();

  // Security: only respond to the configured chat
  if (chatId !== env.TELEGRAM_CHAT_ID) return;

  try {
    if (text.startsWith('/')) {
      await handleCommand(text, chatId, env);
    } else {
      await handleConversation(text, chatId, env);
    }
  } catch (err) {
    await sendTelegram(chatId, `⚠️ Error: ${err.message}`, env.TELEGRAM_BOT_TOKEN);
  }
}

// ---------------------------------------------------------------------------
// Command handler — triggers GitHub Actions workflow
// ---------------------------------------------------------------------------

async function handleCommand(text, chatId, env) {
  const cmd     = text.split(' ')[0].toLowerCase();
  const command = COMMANDS[cmd];

  if (!command) {
    const available = Object.keys(COMMANDS).join(', ');
    await sendTelegram(chatId, `Unknown command.\nAvailable: ${available}`, env.TELEGRAM_BOT_TOKEN);
    return;
  }

  // Acknowledge immediately
  await sendTelegram(
    chatId,
    `⏳ <b>${command.label}</b> running…\nI'll message you when done.`,
    env.TELEGRAM_BOT_TOKEN,
  );

  const ok = await triggerWorkflow(command.workflow, env);
  if (!ok) {
    await sendTelegram(
      chatId,
      `⚠️ Failed to trigger ${command.workflow}. Check GitHub Actions.`,
      env.TELEGRAM_BOT_TOKEN,
    );
  }
}

// ---------------------------------------------------------------------------
// Conversational handler — Notion context + Claude API
// ---------------------------------------------------------------------------

async function handleConversation(text, chatId, env) {
  // Typing indicator (best-effort)
  await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendChatAction`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, action: 'typing' }) },
  ).catch(() => {});

  const lower = text.toLowerCase();
  const isSpendingQuery = SPENDING_KEYWORDS.some(kw => lower.includes(kw));

  const [context, spendingContext] = await Promise.all([
    fetchNotionContext(env),
    isSpendingQuery ? fetchSpendingContext(text, env) : Promise.resolve(''),
  ]);

  const fullContext = spendingContext
    ? context + '\n\n' + spendingContext
    : context;

  const rawReply = await callClaude(text, fullContext, env);

  // Phase 16: Claude may embed [FIN_UPDATE]{...}[/FIN_UPDATE] in its reply
  // when it detects a financial update. Parse it, write to Notion, then
  // strip the block from the user-facing message.
  const { cleanReply, updates } = parseFinancialUpdates(rawReply);

  let suffix = '';
  let anyWritten = false;
  for (const payload of updates) {
    const ok = await createFinancialUpdate(payload, env);
    if (ok) anyWritten = true;
    suffix += ok
      ? `\n\n✓ Recorded to Notion. Auto-syncing to Sheets + Supabase…`
      : `\n\n⚠️ Failed to record to Notion. Try again or add the row manually.`;
  }

  // Phase 16: if any Financial Updates rows got written, immediately trigger
  // bot_sync.yml so the user sees the change in the web app within ~1 minute
  // (instead of waiting for the daily 16:30 BST run or a manual Sync click).
  if (anyWritten) {
    const dispatched = await triggerWorkflow('bot_sync.yml', env);
    suffix += dispatched
      ? `\n→ Sync triggered. Telegram will confirm when complete (~1–2 min).`
      : `\n→ Sync auto-trigger failed — click Sync in the app or send /sync.`;
  }

  await sendTelegram(chatId, cleanReply + suffix, env.TELEGRAM_BOT_TOKEN);
}

// ---------------------------------------------------------------------------
// Phase 16: parse [FIN_UPDATE]{...}[/FIN_UPDATE] blocks from Claude's reply
// ---------------------------------------------------------------------------

function parseFinancialUpdates(reply) {
  const updates = [];
  const re = /\[FIN_UPDATE\]\s*(\{[\s\S]*?\})\s*\[\/FIN_UPDATE\]/g;
  let cleanReply = reply;
  let match;
  while ((match = re.exec(reply)) !== null) {
    try {
      updates.push(JSON.parse(match[1]));
    } catch (err) {
      // Bad JSON — leave the block in the visible reply so the user notices
      continue;
    }
  }
  cleanReply = reply.replace(re, '').trim();
  return { cleanReply, updates };
}

// ---------------------------------------------------------------------------
// Phase 16: create a Financial Updates row in Notion
// ---------------------------------------------------------------------------

async function createFinancialUpdate(payload, env) {
  const today = new Date().toISOString().slice(0, 10);
  const props = {
    Title:    { title:     [{ type: 'text', text: { content: payload.title || autoTitle(payload) } }] },
    Type:     { select:    { name: payload.type } },
    Domain:   { select:    { name: payload.domain } },
    Status:   { select:    { name: 'confirmed' } },
    Source:   { select:    { name: 'nl_mobile' } },
    'Event Date':    { date: { start: payload.event_date || today } },
    'Sheets Written':   { checkbox: false },
    'Supabase Written': { checkbox: false },
  };

  if (payload.account)       props['Account']       = { rich_text: [{ type: 'text', text: { content: payload.account } }] };
  if (payload.from_account)  props['From Account']  = { rich_text: [{ type: 'text', text: { content: payload.from_account } }] };
  if (payload.to_account)    props['To Account']    = { rich_text: [{ type: 'text', text: { content: payload.to_account } }] };
  if (payload.new_balance != null) props['New Balance'] = { number: Number(payload.new_balance) };
  if (payload.amount != null)      props['Amount']      = { number: Number(payload.amount) };
  if (payload.ticker)        props['Ticker'] = { rich_text: [{ type: 'text', text: { content: payload.ticker } }] };
  if (payload.qty   != null) props['Qty']    = { number: Number(payload.qty) };
  if (payload.price != null) props['Price']  = { number: Number(payload.price) };
  if (payload.notes)         props['Notes']  = { rich_text: [{ type: 'text', text: { content: payload.notes } }] };

  try {
    const resp = await fetch('https://api.notion.com/v1/pages', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.NOTION_API_KEY}`,
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        parent:     { database_id: NOTION_FINANCIAL_UPDATES_DB_ID },
        properties: props,
      }),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

function autoTitle(p) {
  if (p.type === 'BALANCE_UPDATE') {
    return `${p.account || p.domain} → £${Number(p.new_balance).toLocaleString()}`;
  }
  if (p.type === 'TRANSFER') {
    return `${p.from_account} → ${p.to_account} (£${Number(p.amount).toLocaleString()})`;
  }
  if (p.type === 'BUY' || p.type === 'SELL') {
    return `${p.type} ${p.qty} ${p.ticker} @ £${Number(p.price).toLocaleString()}`;
  }
  return `${p.type} £${Number(p.amount).toLocaleString()} · ${p.account || p.domain}`;
}

// ---------------------------------------------------------------------------
// Notion context fetch
// ---------------------------------------------------------------------------

async function fetchNotionContext(env) {
  const [
    agentConfig, memoryIndex, investments, userProfile, sheetStructure,
    savings, pensions, accounts,
  ] = await Promise.all([
    fetchNotionPage(NOTION_AGENT_CONFIG_ID, env.NOTION_API_KEY),
    fetchNotionPage(NOTION_MEMORY_INDEX_ID, env.NOTION_API_KEY),
    fetchNotionPage(NOTION_INVESTMENTS_CONTEXT_ID, env.NOTION_API_KEY),
    fetchNotionPage(NOTION_USER_PROFILE_ID, env.NOTION_API_KEY),
    fetchNotionPage(NOTION_SHEET_STRUCTURE_ID, env.NOTION_API_KEY),
    fetchNotionPage(NOTION_SAVINGS_CONTEXT_ID, env.NOTION_API_KEY),
    fetchNotionPage(NOTION_PENSIONS_CONTEXT_ID, env.NOTION_API_KEY),
    fetchNotionPage(NOTION_FINANCE_ACCOUNTS_ID, env.NOTION_API_KEY),
  ]);

  return [
    '=== AGENT CONFIG ===', agentConfig,
    '\n=== USER PROFILE ===', userProfile,
    '\n=== FINANCE ACCOUNTS (authoritative account names) ===', accounts,
    '\n=== GOOGLE SHEET STRUCTURE ===', sheetStructure,
    '\n=== INVESTMENTS CONTEXT (latest snapshot) ===', investments || '(not yet populated)',
    '\n=== SAVINGS CONTEXT (latest snapshot) ===', savings || '(not yet populated)',
    '\n=== PENSIONS CONTEXT (latest snapshot) ===', pensions || '(not yet populated)',
    '\n=== MEMORY INDEX ===', memoryIndex,
  ].join('\n');
}

// ---------------------------------------------------------------------------
// Phase 18: fetch recent Monzo transactions from Supabase for spending queries
// ---------------------------------------------------------------------------

async function fetchSpendingContext(userMessage, env) {
  const url  = env.SUPABASE_URL;
  const key  = env.SUPABASE_ANON_KEY;
  if (!url || !key) return '';

  try {
    // Fetch last 60 transactions ordered by date desc
    const resp = await fetch(
      `${url}/rest/v1/monzo_transactions?select=date,name,emoji,category,type,amount,currency,notes,pot_name,account_type&order=date.desc,time.desc&limit=60`,
      { headers: { 'apikey': key, 'Authorization': `Bearer ${key}` } },
    );
    if (!resp.ok) return '';
    const rows = await resp.json();
    if (!rows?.length) return '';

    const lines = rows.map(r => {
      const amt  = r.amount != null ? (r.amount < 0 ? `-£${Math.abs(r.amount).toFixed(2)}` : `+£${r.amount.toFixed(2)}`) : '';
      const name = [r.emoji, r.name].filter(Boolean).join(' ');
      return `${r.date} | ${name} | ${r.category ?? ''} | ${amt} | ${r.account_type}`;
    });

    return `=== RECENT MONZO TRANSACTIONS (last 60, newest first — query Supabase directly for analysis; never read the raw Google Sheet) ===\ndate | name | category | amount | account\n${lines.join('\n')}`;
  } catch {
    return '';
  }
}

async function fetchNotionPage(pageId, notionKey) {
  try {
    const resp = await fetch(
      `https://api.notion.com/v1/blocks/${pageId}/children?page_size=100`,
      {
        headers: {
          'Authorization': `Bearer ${notionKey}`,
          'Notion-Version': '2022-06-28',
        },
      },
    );
    if (!resp.ok) return '';
    const data = await resp.json();
    return extractNotionText(data.results || []);
  } catch {
    return '';
  }
}

function extractNotionText(blocks) {
  const TEXT_TYPES = [
    'paragraph', 'heading_1', 'heading_2', 'heading_3',
    'bulleted_list_item', 'numbered_list_item', 'to_do',
    'toggle', 'quote', 'callout', 'code',
  ];

  return blocks
    .map(block => {
      const type    = block.type;
      const content = block[type];
      if (!content?.rich_text) return '';
      const line = content.rich_text.map(t => t.plain_text).join('');
      // Add heading markers for readability
      if (type === 'heading_1') return `# ${line}`;
      if (type === 'heading_2') return `## ${line}`;
      if (type === 'heading_3') return `### ${line}`;
      if (type === 'bulleted_list_item') return `• ${line}`;
      return line;
    })
    .filter(Boolean)
    .join('\n');
}

// ---------------------------------------------------------------------------
// Claude API
// ---------------------------------------------------------------------------

async function callClaude(userMessage, context, env) {
  const finUpdateInstructions = `

When the user describes a financial change — a balance update or a money movement — record it to the Notion Financial Updates DB by appending a structured block at the END of your reply:

[FIN_UPDATE]
{
  "type": "BALANCE_UPDATE" | "DEPOSIT" | "WITHDRAWAL" | "TRANSFER" | "BUY" | "SELL",
  "domain": "investments" | "savings" | "pensions",
  "account": "<Company> <Account Name>",
  "from_account": "<Company> <Account Name>",
  "to_account": "<Company> <Account Name>",
  "new_balance": 12345.67,
  "amount": 500.00,
  "ticker": "GOOG",
  "qty": 5,
  "price": 160.00,
  "event_date": "YYYY-MM-DD",
  "notes": "<original user text>"
}
[/FIN_UPDATE]

Rules:
- Use BALANCE_UPDATE when the user states what something is worth now (e.g. "my Aviva pension is now £140k"). Set new_balance only.
- Use DEPOSIT/WITHDRAWAL/TRANSFER/BUY/SELL when money actually moves. Set amount (and for BUY/SELL: ticker, qty, price).
- TRANSFER needs from_account AND to_account; omit account.
- account must use the exact "Company AccountName" format from FINANCE ACCOUNTS (e.g. "Aviva Nationwide Pension", "CMC Invest Cash ISA", "Monzo Our Children"). Do not invent account names.
- event_date defaults to today if not specified.
- Include only the fields relevant to the type — leave the others out.
- In your visible reply (before the block), show the user a one-line confirmation of what you're recording, e.g. "Recording: BALANCE_UPDATE · pensions · Aviva Nationwide Pension → £140,000".
- If the user is asking a question or chatting (no financial event described), do NOT add a [FIN_UPDATE] block.
- Only one [FIN_UPDATE] block per reply.

After your reply is processed, the system auto-confirms the entry in Notion. The user can edit/delete it in Notion if wrong. sync_worker pushes it to Sheets + Supabase on the next /sync.`;

  const systemPrompt = context
    ? `You are Fin Assist, a personal finance AI assistant for a UK retail investor.\n\nContext about this portfolio and investment system:\n${context}\n${finUpdateInstructions}\n\nAnswer concisely. Use plain text (no markdown except the [FIN_UPDATE] block) since the response is sent via Telegram.`
    : 'You are Fin Assist, a personal finance AI assistant for a UK retail investor. Answer concisely in plain text.';

  try {
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key':         env.CLAUDE_API_KEY,
        'anthropic-version': '2023-06-01',
        'Content-Type':      'application/json',
      },
      body: JSON.stringify({
        model:      'claude-opus-4-7',
        max_tokens: 1024,
        system:     systemPrompt,
        messages:   [{ role: 'user', content: userMessage }],
      }),
    });

    if (!resp.ok) {
      const err = await resp.text();
      return `⚠️ Claude API error (${resp.status}): ${err.slice(0, 200)}`;
    }

    const data = await resp.json();
    return data.content?.[0]?.text || '(empty response)';
  } catch (err) {
    return `⚠️ Claude API error: ${err.message}`;
  }
}

// ---------------------------------------------------------------------------
// GitHub Actions workflow_dispatch
// ---------------------------------------------------------------------------

async function triggerWorkflow(workflow, env) {
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${workflow}/dispatches`,
      {
        method:  'POST',
        headers: {
          'Authorization': `Bearer ${env.GH_PAT}`,
          'Accept':        'application/vnd.github+json',
          'Content-Type':  'application/json',
          'User-Agent':    'fin-assist-bot',
        },
        body: JSON.stringify({ ref: 'main' }),
      },
    );
    return resp.status === 204;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Telegram sendMessage
// ---------------------------------------------------------------------------

async function sendTelegram(chatId, text, token) {
  // Telegram message limit is 4096 chars — truncate if needed
  const safeText = text.length > 4096 ? text.slice(0, 4090) + '…' : text;

  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({
      chat_id:    chatId,
      text:       safeText,
      parse_mode: 'HTML',
    }),
  });
}
