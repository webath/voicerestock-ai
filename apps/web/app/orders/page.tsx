import { Suspense } from "react";
import { Loading } from "@/components/ui";
import { OrdersView } from "./OrdersView";

export default function OrdersPage() {
  return (
    <Suspense fallback={<Loading />}>
      <OrdersView />
    </Suspense>
  );
}
