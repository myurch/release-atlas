/** Keep live requests on the current origin, including the portfolio mount. */
export function apiPath(
  path: string,
  pathname = window.location.pathname,
): string {
  const mount =
    pathname === "/release-atlas" || pathname.startsWith("/release-atlas/")
      ? "/release-atlas"
      : "";
  return `${mount}/api/${path}`;
}
