import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Airflow Sales",
    template: "%s · Airflow Sales",
  },
  description:
    "Agentic sales intelligence: research, qualify, critique and route opportunities for human approval.",
};

const themeBootstrap = `(function(){try{var k="airflow-sales:theme";var v=localStorage.getItem(k);if(v!=="light"&&v!=="dark"){v="light";}document.documentElement.dataset.theme=v;}catch(e){document.documentElement.dataset.theme="light";}})();`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
