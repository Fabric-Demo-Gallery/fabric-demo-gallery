"use client";

import { AuthProvider } from "@/lib/AuthProvider";
import { useAuth } from "@/lib/AuthProvider";
import type { ReactNode } from "react";

function Navbar() {
  const { account, login, logout, initialized } = useAuth();

  return (
    <header className="bg-white border-b border-[#e0e0e0] sticky top-0 z-50">
      <div className="mx-auto max-w-[1280px] flex items-center justify-between px-8 h-[48px]">
        <div className="flex items-center gap-5">
          <a href="/" className="flex items-center gap-2.5 text-[15px] font-semibold text-[#242424] hover:no-underline">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <rect width="8" height="8" rx="1" fill="#0078d4"/>
              <rect x="10" width="8" height="8" rx="1" fill="#0078d4" opacity="0.6"/>
              <rect y="10" width="8" height="8" rx="1" fill="#0078d4" opacity="0.6"/>
              <rect x="10" y="10" width="8" height="8" rx="1" fill="#0078d4"/>
            </svg>
            Fabric Demo Gallery
          </a>
          <span className="text-[#d1d1d1]">|</span>
          <a href="/" className="text-[14px] text-[#616161] hover:text-[#242424]">Demos</a>
          <a href="https://github.com/microsoft/skills-for-fabric" target="_blank" rel="noopener noreferrer" className="text-[14px] text-[#616161] hover:text-[#242424]">GitHub</a>
        </div>
        <div className="flex items-center gap-3">
          {initialized && (
            account ? (
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <div className="w-[28px] h-[28px] rounded-full bg-[#0f6cbd] flex items-center justify-center text-white text-[12px] font-semibold">
                    {account.username?.charAt(0).toUpperCase()}
                  </div>
                  <span className="text-[13px] text-[#616161] hidden md:inline">{account.username}</span>
                </div>
                <button onClick={logout} className="text-[13px] text-[#616161] hover:text-[#242424]">Sign out</button>
              </div>
            ) : (
              <button onClick={login} className="rounded-[4px] bg-[#0f6cbd] px-4 py-[5px] text-[13px] font-medium text-white hover:bg-[#115ea3] active:bg-[#0c5a9e] transition-colors">
                Sign in
              </button>
            )
          )}
        </div>
      </div>
    </header>
  );
}

export default function ClientShell({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <Navbar />
      <main>{children}</main>
    </AuthProvider>
  );
}
