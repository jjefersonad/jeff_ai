/**
 * Primary nav entries shared by `NavSidebar` and unit tests.
 */

import {
  BarChart3,
  BriefcaseBusiness,
  CalendarClock,
  ImageIcon,
  Mail,
  MessageCircle,
  MessagesSquare,
  Plug,
  Users,
} from "lucide-react";

import type { AuthRole } from "@/providers/AuthProvider";

export interface NavEntry {
  label: string;
  href: string;
  description: string;
  icon: React.ComponentType<Record<string, unknown>>;
  match: (pathname: string) => boolean;
  /** When set, the entry is only shown for that role (admin-only surfaces). */
  requireRole?: AuthRole;
}

export const NAV_ENTRIES: readonly NavEntry[] = [
  {
    label: "Chat",
    href: "/",
    description: "Back to the conversation",
    icon: MessagesSquare,
    match: (p) => p === "/",
  },
  {
    label: "Images",
    href: "/images",
    description: "Browse generated and reference images",
    icon: ImageIcon,
    match: (p) => p === "/images" || p.startsWith("/images/"),
  },
  {
    label: "MCP Servers",
    href: "/mcp-servers",
    description: "Manage Model Context Protocol servers",
    icon: Plug,
    match: (p) => p === "/mcp-servers" || p.startsWith("/mcp-servers/"),
  },
  {
    label: "Consumo",
    href: "/usage",
    description: "Token usage by period (admin)",
    icon: BarChart3,
    match: (p) => p === "/usage" || p.startsWith("/usage/"),
    requireRole: "admin",
  },
  {
    label: "Usuários",
    href: "/admin/users",
    description: "Gerenciar usuários (admin)",
    icon: Users,
    match: (p) => p === "/admin/users" || p.startsWith("/admin/users/"),
    requireRole: "admin",
  },
  {
    label: "Integrações",
    href: "/integrations",
    description: "Link your account to other channels (WhatsApp, Telegram)",
    icon: MessageCircle,
    match: (p) => p === "/integrations" || p.startsWith("/integrations/"),
  },
  {
    label: "Agendamentos",
    href: "/scheduling",
    description: "Manage scheduled tasks",
    icon: CalendarClock,
    match: (p) => p === "/scheduling" || p.startsWith("/scheduling/"),
  },
  {
    label: "CRM",
    href: "/crm",
    description: "Contacts, companies, and deals",
    icon: BriefcaseBusiness,
    match: (p) => p === "/crm" || p.startsWith("/crm/"),
  },
  {
    label: "Email",
    href: "/email",
    description: "Inbox and connected IMAP/SMTP accounts",
    icon: Mail,
    match: (p) => p === "/email" || p.startsWith("/email/"),
  },
];

/** Visible nav entries for the current auth role (REQ-006 admin-only usage). */
export function getVisibleNavEntries(
  role: AuthRole | null | undefined
): NavEntry[] {
  return NAV_ENTRIES.filter(
    (entry) => !entry.requireRole || entry.requireRole === role
  );
}
