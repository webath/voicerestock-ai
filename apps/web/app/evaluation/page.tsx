import { Suspense } from "react";
import { PageSkeleton } from "@/components/ui";
import EvaluationView from "./view";

export default function EvaluationPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <EvaluationView />
    </Suspense>
  );
}
