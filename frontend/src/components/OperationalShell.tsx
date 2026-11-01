import type { ComponentPropsWithoutRef } from "react";
// Shared semantic shell for organization workspaces. Colors live in tokens.css;
// shared controls and role-specific layouts use design-system.css.
export function OperationalSidebar(props: ComponentPropsWithoutRef<"aside">) {
  return <aside {...props} />;
}
export function SidebarNavButton({
  type = "button",
  ...props
}: ComponentPropsWithoutRef<"button">) {
  return <button type={type} {...props} />;
}
