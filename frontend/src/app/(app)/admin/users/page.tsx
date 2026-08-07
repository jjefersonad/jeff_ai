"use client";

/**
 * Admin-only user management page.
 *
 * Implements the `user-management-ui` spec (REQ-001 in this change) by
 * guarding `/admin/users` against any non-admin user. The pattern follows
 * the same `useEffect`-driven redirect used by the `usage` page (see
 * `frontend/src/app/(app)/usage/page.tsx`, REQ-006 of
 * `token-usage-reporting`): when the role is known and is not `admin`, we
 * `router.replace("/")` and render `null` so no admin-only data leaks before
 * the navigation completes.
 *
 * REQ-002 (user-management-ui, frontend-2): the table also exposes a
 * client-side role filter (Radix `Select`) over the data returned by
 * `GET /api/admin/users`. The list already comes from the backend filtered
 * by what each admin is allowed to see; this filter is a presentation
 * affordance over the loaded data, not a network round-trip.
 *
 * REQ-003 (user-management-ui, frontend-3): the create form above the
 * listing calls `POST /api/admin/users`. On success the new user is
 * appended to the local list (no full reload) and the form is reset. On
 * failure the typed values are preserved and the API's error message is
 * shown inline with `role="alert"`, so the admin can correct just the bad
 * field without retyping everything.
 *
 * REQ-004 (user-management-ui, frontend-4): each row's `Status` cell
 * exposes a Switch bound to `u.is_active`. Clicking the switch calls
 * `patchAdminUser(id, { is_active: <opposite> })`. The local row state is
 * updated PESSIMISTICALLY — only on a successful 200 response — so a 409
 * (auto-lockout / last-admin) leaves the row visually unchanged. The error
 * message is rendered inline below the table, scoped to the offending
 * `userId`, and clears when the admin changes any toggle again.
 *
 * REQ-005 (user-management-ui, frontend-5) is a NavSidebar-only change —
 * the item "Usuários" is added to the sidebar, hidden for non-admins.
 */

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/providers/AuthProvider";
import {
  createAdminUser,
  fetchAdminUsers,
  patchAdminUser,
  type AdminUser,
} from "@/app/lib/adminUsers";

type RoleFilter = "all" | "admin" | "user";
type CreateRole = "admin" | "user";

const ROLE_FILTERS: { value: RoleFilter; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "admin", label: "Admin" },
  { value: "user", label: "Usuário" },
];

const CREATE_ROLES: { value: CreateRole; label: string }[] = [
  { value: "user", label: "Usuário" },
  { value: "admin", label: "Admin" },
];

function formatDate(iso: string): string {
  // Backend returns ISO-8601; we just render YYYY-MM-DD for the table.
  return iso.slice(0, 10);
}

interface CreateAdminUserError extends Error {
  status?: number;
}

export default function UsersPage() {
  const router = useRouter();
  const { user, isRehydrating } = useAuth();

  // REQ-001 (user-management-ui): block non-admin direct URL access once
  // role is known. Same pattern as the `usage` page (token-usage-reporting
  // REQ-006) — redirect off the route before any admin data is rendered.
  // Wait for AuthProvider's `/api/me` probe so a hard reload does not
  // briefly treat a valid admin session as "no user".
  useEffect(() => {
    if (isRehydrating) return;
    if (user && user.role !== "admin") {
      router.replace("/");
    }
  }, [user, isRehydrating, router]);

  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("all");
  // Defer Radix Selects until after mount to avoid SSR/client aria-controls
  // hydration mismatches (Next.js react-hydration-error on SelectTrigger).
  const [selectsReady, setSelectsReady] = useState(false);

  // Create form state.
  const [createUsername, setCreateUsername] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createRole, setCreateRole] = useState<CreateRole>("user");
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  // REQ-004 (user-management-ui, frontend-4): per-row patch state.
  // We keep a `Set` of userIds that are mid-PATCH so the corresponding
  // switch can be disabled (no double-clicks) and we hold a map of
  // `userId -> errorMessage` so a 409 from the auto-lockout guard can be
  // rendered next to the offending row, scoped to that row only.
  const [patchingIds, setPatchingIds] = useState<ReadonlySet<string>>(
    () => new Set<string>()
  );
  const [patchErrorById, setPatchErrorById] = useState<
    Record<string, string>
  >({});

  useEffect(() => {
    setSelectsReady(true);
  }, []);

  useEffect(() => {
    if (isRehydrating) return;
    if (!user || user.role !== "admin") return;
    let cancelled = false;
    fetchAdminUsers()
      .then((data) => {
        if (!cancelled) setUsers(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(
          err instanceof Error ? err.message : "Erro ao carregar usuários"
        );
      });
    return () => {
      cancelled = true;
    };
  }, [user, isRehydrating]);

  const visibleUsers = useMemo(() => {
    if (!users) return [];
    if (roleFilter === "all") return users;
    return users.filter((u) => u.role === roleFilter);
  }, [users, roleFilter]);

  // REQ-003 (user-management-ui): create form submit. On success the new
  // user is appended to the local list (no full reload) and the form is
  // reset. On failure (e.g. 422 password too short, 409 username taken)
  // the typed values are preserved and the API's error message is shown
  // inline — same `role="alert"` pattern as `usage`'s error block.
  const onCreateSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      const created = await createAdminUser({
        username: createUsername,
        password: createPassword,
        role: createRole,
      });
      setUsers((prev) => (prev ? [...prev, created] : [created]));
      setCreateUsername("");
      setCreatePassword("");
      setCreateRole("user");
    } catch (err: unknown) {
      const e = err as CreateAdminUserError;
      setCreateError(
        e instanceof Error ? e.message : "Erro ao criar usuário"
      );
    } finally {
      setCreating(false);
    }
  };

  // REQ-004 (user-management-ui, frontend-4): pessimistic status toggle.
  // Click the switch for a row → call PATCH with the OPPOSITE of the
  // current value. On success, replace that row in the local list. On
  // failure (esp. 409 auto-lockout), surface the error scoped to the
  // offending userId and leave the row visually unchanged (no optimistic
  // update to revert). The switch is disabled while the PATCH is in
  // flight to prevent double-clicks.
  const onToggleStatus = async (user: AdminUser) => {
    if (patchingIds.has(user.id)) return;
    const nextIsActive = !user.is_active;
    setPatchingIds((prev) => {
      const next = new Set(prev);
      next.add(user.id);
      return next;
    });
    // Clear any prior error for this row before the new attempt.
    setPatchErrorById((prev) => {
      if (!(user.id in prev)) return prev;
      const next = { ...prev };
      delete next[user.id];
      return next;
    });
    try {
      const updated = await patchAdminUser(user.id, {
        is_active: nextIsActive,
      });
      setUsers((prev) =>
        prev === null
          ? prev
          : prev.map((u) => (u.id === user.id ? updated : u))
      );
    } catch (err: unknown) {
      const e = err as Error;
      setPatchErrorById((prev) => ({
        ...prev,
        [user.id]: e instanceof Error ? e.message : "Erro ao atualizar usuário",
      }));
    } finally {
      setPatchingIds((prev) => {
        const next = new Set(prev);
        next.delete(user.id);
        return next;
      });
    }
  };

  if (user && user.role !== "admin") {
    return null;
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[960px] items-center gap-3 px-6 py-4">
          <Users size={24} className="text-primary" aria-hidden="true" />
          <h1 className="text-xl font-semibold">Usuários</h1>
        </div>
      </header>

      <main className="mx-auto flex max-w-[960px] flex-col gap-6 px-6 py-8">
        <form
          onSubmit={onCreateSubmit}
          className="flex flex-col gap-4 rounded-md border border-border bg-card p-4"
          aria-label="Criar usuário"
        >
          <h2 className="text-sm font-semibold">Criar usuário</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="create-username">Usuário</Label>
              <Input
                id="create-username"
                value={createUsername}
                onChange={(e) => setCreateUsername(e.target.value)}
                autoComplete="off"
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="create-password">Senha</Label>
              <Input
                id="create-password"
                type="password"
                value={createPassword}
                onChange={(e) => setCreatePassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="create-role">Role</Label>
              {selectsReady ? (
                <Select
                  value={createRole}
                  onValueChange={(v) => setCreateRole(v as CreateRole)}
                >
                  <SelectTrigger id="create-role" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CREATE_ROLES.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <select
                  id="create-role"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={createRole}
                  onChange={(e) => setCreateRole(e.target.value as CreateRole)}
                >
                  {CREATE_ROLES.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div className="flex items-end">
              <Button
                type="submit"
                disabled={creating}
                className="w-full sm:w-auto"
              >
                {creating ? "Criando..." : "Criar"}
              </Button>
            </div>
          </div>
          {createError && (
            <p className="text-sm text-destructive" role="alert">
              {createError}
            </p>
          )}
        </form>

        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-2">
            <label
              htmlFor="users-role-filter"
              className="text-sm font-medium text-foreground"
            >
              Filtrar por role
            </label>
            {selectsReady ? (
              <Select
                value={roleFilter}
                onValueChange={(v) => setRoleFilter(v as RoleFilter)}
              >
                <SelectTrigger
                  id="users-role-filter"
                  className="w-48"
                  aria-label="Filtrar por role"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLE_FILTERS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <select
                id="users-role-filter"
                aria-label="Filtrar por role"
                className="flex h-10 w-48 rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value as RoleFilter)}
              >
                {ROLE_FILTERS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        {loadError && (
          <p className="text-sm text-destructive" role="alert">
            {loadError}
          </p>
        )}

        {users === null && !loadError && (
          <div className="space-y-2" aria-busy="true">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        )}

        {users !== null && (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Usuário
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Role
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Status
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Criado em
                  </th>
                </tr>
              </thead>
              <tbody>
                {visibleUsers.length === 0 ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-6 text-center text-muted-foreground"
                    >
                      Nenhum usuário para o filtro selecionado.
                    </td>
                  </tr>
                ) : (
                  visibleUsers.map((u) => (
                    <tr key={u.id} className="border-t border-border">
                      <td className="px-4 py-2 font-mono">{u.username}</td>
                      <td className="px-4 py-2">{u.role}</td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          <Switch
                            checked={u.is_active}
                            disabled={patchingIds.has(u.id)}
                            onCheckedChange={() => onToggleStatus(u)}
                            aria-label={
                              u.is_active
                                ? `Desativar ${u.username}`
                                : `Ativar ${u.username}`
                            }
                          />
                          <span className="text-sm text-muted-foreground">
                            {u.is_active ? "Ativo" : "Inativo"}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-2 text-muted-foreground">
                        {formatDate(u.created_at)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {Object.entries(patchErrorById).map(([userId, message]) =>
          message ? (
            <p
              key={userId}
              className="text-sm text-destructive"
              role="alert"
            >
              {message}
            </p>
          ) : null
        )}
      </main>
    </div>
  );
}
