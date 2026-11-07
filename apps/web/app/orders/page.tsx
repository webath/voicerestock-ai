import { Suspense } from "react";
import { PageSkeleton } from "@/components/ui";
import OrdersView from "./view";

export default function OrdersPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <OrdersView />
    </Suspense>
  );
}
