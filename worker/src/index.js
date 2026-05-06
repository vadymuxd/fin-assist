/**
 * fin-assist-bot — Cloudflare Worker
 *
 * Receives Telegram webhook updates and routes them:
 *   /holdings  → triggers bot_analyse.yml  — event-driven holdings check with full status
 *   /discover  → triggers bot_scan.yml     — dynamic prospect discovery from Reddit/news/trending
 *   /digest    → triggers bot_digest.yml   — weekly digest
 *   /snapshot  → triggers bot_snapshot.yml — Notion portfolio snapshot refresh
 *   (legacy /analyse + /scan still route to the same workflows as aliases)
 *   free text  → fetches Notion context, calls Claude API, replies inline
 *
 * Required secrets (set via `wrangler secret put`):
 *   TELEGRAM_BOT_TOKEN  — bot token from @BotFather
 *   TELEGRAM_CHAT_ID    — your personal chat ID (security filter)
 *   GH_PAT              — GitHub PAT with actions:write scope
 *   NOTION_API_KEY      — Notion integration token
 *   CLAUDE_API_KEY      — Anthropic API key
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
  '/snapshot': { workflow: 'bot_snapshot.yml',     label: 'Portfolio snapshot' },
  '/mortgage': { workflow: 'mortgage_monitor.yml', label: 'Mortgage monitor'   },
  '/sync':     { workflow: 'bot_sync.yml',         label: 'Sync snapshots'    },
  // Legacy aliases — keep old commands working
  '/analyse':  { workflow: 'bot_analyse.yml',      label: 'Holdings check'     },
  '/scan':     { workflow: 'bot_scan.yml',         label: 'Prospect discovery' },
};

// Notion page IDs for context
const NOTION_AGENT_CONFIG_ID    = '33f416f2-7566-811a-a994-e1a3561adac7';
const NOTION_MEMORY_INDEX_ID    = '33f416f2-7566-812a-8b25-fea944567cab';
const NOTION_SNAPSHOT_PAGE_ID   = '33f416f2-7566-81ce-b7e8-dd7b68101342';
const NOTION_USER_PROFILE_ID    = '33f416f2-7566-81f4-b5f7-dc7bbfb7e626';
const NOTION_SHEET_STRUCTURE_ID = '33f416f2-7566-81b0-82c3-cfddebca3d9f';

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

  const context = await fetchNotionContext(env);
  const reply   = await callClaude(text, context, env);

  await sendTelegram(chatId, reply, env.TELEGRAM_BOT_TOKEN);
}

// ---------------------------------------------------------------------------
// Notion context fetch
// ---------------------------------------------------------------------------

async function fetchNotionContext(env) {
  const [agentConfig, memoryIndex, snapshot, userProfile, sheetStructure] = await Promise.all([
    fetchNotionPage(NOTION_AGENT_CONFIG_ID, env.NOTION_API_KEY),
    fetchNotionPage(NOTION_MEMORY_INDEX_ID, env.NOTION_API_KEY),
    fetchNotionPage(NOTION_SNAPSHOT_PAGE_ID, env.NOTION_API_KEY),
    fetchNotionPage(NOTION_USER_PROFILE_ID, env.NOTION_API_KEY),
    fetchNotionPage(NOTION_SHEET_STRUCTURE_ID, env.NOTION_API_KEY),
  ]);

  return [
    '=== AGENT CONFIG ===', agentConfig,
    '\n=== USER PROFILE ===', userProfile,
    '\n=== GOOGLE SHEET STRUCTURE ===', sheetStructure,
    '\n=== PORTFOLIO SNAPSHOT (latest /snapshot run) ===', snapshot || '(not yet populated — user must run /snapshot first)',
    '\n=== MEMORY INDEX ===', memoryIndex,
  ].join('\n');
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
  const systemPrompt = context
    ? `You are Fin Assist, a personal finance AI assistant for a UK retail investor.\n\nContext about this portfolio and investment system:\n${context}\n\nAnswer concisely. Use plain text (no markdown) since the response is sent via Telegram.`
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
