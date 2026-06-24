import StudentAppShell from "@/components/shell/StudentAppShell";

export default function MainLayout({ children }: { children: React.ReactNode }) {
  return <StudentAppShell>{children}</StudentAppShell>;
}
