// ── MasterSAT design system — component library barrel ──────────────
// Foundations
export { Button } from "./Button";
export type { ButtonProps, ButtonVariant, ButtonSize } from "./Button";
export { Spinner } from "./Spinner";
export { Input } from "./Input";
export type { InputProps } from "./Input";
export { Textarea } from "./Textarea";
export type { TextareaProps } from "./Textarea";
export { Select } from "./Select";
export type { SelectProps } from "./Select";
export { Checkbox } from "./Checkbox";
export type { CheckboxProps } from "./Checkbox";
export { Switch } from "./Switch";
export type { SwitchProps } from "./Switch";
export { Field } from "./Field";
export type { FieldProps } from "./Field";
export { IconButton } from "./IconButton";
export type { IconButtonVariant } from "./IconButton";

// Surfaces & layout
export {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  CardSectionTitle,
} from "./Card";
export type { CardVariant } from "./Card";
export { Container, Stack, PageHeading } from "./layout";
export { PageHeader } from "./PageHeader";
export { Separator } from "./Separator";

// Disclosure & navigation
export { Tabs } from "./Tabs";
export type { TabItem, TabsProps } from "./Tabs";
export { SegmentedControl } from "./SegmentedControl";
export type { Segment } from "./SegmentedControl";
export { Accordion } from "./Accordion";
export type { AccordionItem } from "./Accordion";
export { DropdownMenu, DropdownMenuItem } from "./DropdownMenu";
export { Pagination } from "./Pagination";
export {
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableHeaderCell,
  TableCell,
} from "./Table";

// Overlays
export { Modal } from "./Modal";
export type { ModalProps } from "./Modal";
export { Drawer } from "./Drawer";
export type { DrawerProps } from "./Drawer";
export { Tooltip } from "./Tooltip";
export { ToastProvider, useToast } from "./Toast";
export type { ToastTone } from "./Toast";

// Display & feedback
export { Badge } from "./Badge";
export type { BadgeVariant } from "./Badge";
export { Alert } from "./Alert";
export type { AlertTone } from "./Alert";
export { Avatar } from "./Avatar";
export type { AvatarProps } from "./Avatar";
export { Progress } from "./Progress";
export type { ProgressTone } from "./Progress";
export { ProgressRing } from "./ProgressRing";
export { Skeleton, SkeletonText } from "./Skeleton";
export { EmptyState } from "./EmptyState";
export { Stat } from "./Stat";
export type { StatProps } from "./Stat";
export { StatCard } from "./StatCard";
export { ActivityItem } from "./ActivityItem";
export { MiniBarChart } from "./MiniBarChart";

// Charts live in their own entry point: `@/components/ui/charts`. They are kept
// OUT of this barrel on purpose — importing them here pulled Recharts into the
// first-load JS of every page that touches the design system. Chart consumers
// import directly from "@/components/ui/charts" (Recharts is then a single,
// on-demand async chunk).
