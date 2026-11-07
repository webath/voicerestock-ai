import { Suspense } from "react";
import { PageSkeleton } from "@/components/ui";
import OverviewView from "./view";

export default function Home() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <OverviewView />
    </Suspense>
  );
}
