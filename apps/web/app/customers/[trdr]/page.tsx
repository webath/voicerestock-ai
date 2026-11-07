import { Suspense } from "react";
import { PageSkeleton } from "@/components/ui";
import CustomerView from "./view";

export default function CustomerPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <CustomerView />
    </Suspense>
  );
}
