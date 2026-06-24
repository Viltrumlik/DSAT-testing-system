"use client";

import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { authApi } from "@/lib/api";

export default function FrozenPage() {
    const queryClient = useQueryClient();
    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-blue-900 flex items-center justify-center p-6">
            <div className="w-full max-w-lg bg-white rounded-3xl shadow-2xl border border-slate-200 p-10 text-center">
                <img src="/images/logo.png" alt="MasterSAT" className="w-20 h-20 object-contain mx-auto mb-5" />
                <h1 className="text-2xl font-black text-slate-900">Account Temporarily Frozen</h1>
                <p className="mt-3 text-slate-600 font-medium">
                    You can sign in, but actions are disabled for this account.
                    Please contact an administrator to reactivate your access.
                </p>
                <div className="mt-7 flex items-center justify-center gap-3">
                    <Link href="/" className="px-5 py-2.5 rounded-xl bg-slate-900 text-white font-bold text-sm">
                        Go Home
                    </Link>
                    <button
                        type="button"
                        onClick={() => {
                            void authApi.logout(queryClient);
                        }}
                        className="px-5 py-2.5 rounded-xl border border-slate-300 text-slate-700 font-bold text-sm"
                    >
                        Sign Out
                    </button>
                </div>
            </div>
        </div>
    );
}
