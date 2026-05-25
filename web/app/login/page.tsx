import LoginForm from "./login-form";

export const metadata = { title: "Sign in" };

type SearchParams = Promise<{ from?: string }>;

export default async function LoginPage({ searchParams }: { searchParams: SearchParams }) {
  const { from } = await searchParams;
  return <LoginForm from={from && from.startsWith("/") ? from : "/"} />;
}
