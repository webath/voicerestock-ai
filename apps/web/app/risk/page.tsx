import { Suspense } from "react";
import { Loading } from "@/components/ui";
import { RiskView } from "./RiskView";

export default function RiskPage() {
  return (
    <Suspense fallback={<Loading />}>
      <RiskView />
    </Suspense>
  );
}
