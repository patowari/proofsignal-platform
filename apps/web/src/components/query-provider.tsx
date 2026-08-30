"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Verification data is a point-in-time record; refetching on every
            // window focus adds load without adding information.
            refetchOnWindowFocus: false,
            staleTime: 30_000,
            retry: (failureCount, error) => {
              // Never retry a rate-limited or missing resource: one wastes the
              // user's remaining budget, the other will never appear.
              const status = (error as { status?: number })?.status;
              if (status === 429 || status === 404) return false;
              return failureCount < 2;
            },
          },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
