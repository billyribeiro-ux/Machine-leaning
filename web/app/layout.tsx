import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Scanify - Professional Trading Scanner',
  description: 'Real-time trading signals powered by machine learning. Get institutional-grade market analysis and alerts.',
  keywords: ['trading', 'scanner', 'signals', 'stocks', 'options', 'machine learning'],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
