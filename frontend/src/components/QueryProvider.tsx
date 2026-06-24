"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useEffect, useState } from "react";
import AuthResilienceSubscriber from "@/components/AuthResilienceSubscriber";
import AuthTabSync from "@/components/AuthTabSync";
import { installAuthTelemetryGlobal } from "@/lib/auth/authConcurrency";
import {
  flushAuthTelemetryQueue,
  startAuthTelemetryFlushLoop,
  stopAuthTelemetryFlushLoop,
} from "@/lib/auth/authClientTelemetry";

export default function QueryProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    installAuthTelemetryGlobal();
    startAuthTelemetryFlushLoop();
    void flushAuthTelemetryQueue();
    return () => stopAuthTelemetryFlushLoop();
  }, []);

  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: (failureCount, error: any) => {
              const status = error?.response?.status;
              if (status === 401 || status === 403) return false;
              return failureCount < 2;
            },
            refetchOnWindowFocus: false,
            staleTime: 15_000,
          },
          mutations: {
            retry: (failureCount, error: any) => {
              const status = error?.response?.status;
              if (status === 401 || status === 403) return false;
              return failureCount < 1;
            },
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={client}>
      <AuthResilienceSubscriber />
      <AuthTabSync />
      {children}
      {process.env.NODE_ENV === "development" ? <ReactQueryDevtools initialIsOpen={false} /> : null}
    </QueryClientProvider>
  );
}

