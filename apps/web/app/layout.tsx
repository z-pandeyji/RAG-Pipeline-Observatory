import type { Metadata } from "next";

import "@xyflow/react/dist/style.css";
import "./globals.css";

export const metadata: Metadata = {
  description: "RAG learning workspace for PDFs",
  title: "RAG Learning"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
