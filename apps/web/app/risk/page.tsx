import { Suspense } from "react";
import { PageSkeleton } from "@/components/ui";
import RiskView from "./view";

export default function RiskPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <RiskView />
    </Suspense>
  );
}
