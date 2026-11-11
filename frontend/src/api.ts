export async function api<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    signal,
  });
  const raw = await response.text();
  let data: unknown;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    throw new Error(
      `The API returned an invalid response (${response.status}). Check that the local FlowPilot service is running.`,
    );
  }
  if (!response.ok) {
    const obj = data as Record<string, unknown> | null;
    const message = obj?.detail ?? obj?.error ?? obj?.message;
    throw new Error(
      typeof message === "string"
        ? message
        : message
          ? JSON.stringify(message)
          : `Request failed (${response.status}).`,
    );
  }
  return data as T;
}
export const isActive = (status?: string) =>
  status === "queued" || status === "running";
export const readable = (value?: string) =>
  value
    ? value.replace(/[_-]/g, " ").replace(/^\w/, (c) => c.toUpperCase())
    : "Unknown";
export const duration = (ms?: number | null) =>
  ms == null
    ? "Unknown"
    : ms < 1000
      ? `${Math.round(ms)} ms`
      : `${(ms / 1000).toFixed(1)} s`;
export const dateTime = (value?: string) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Unknown";
export const errorMessage = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
export function download(name: string, value: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
