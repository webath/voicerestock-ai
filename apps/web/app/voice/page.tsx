import { Suspense } from "react";
import { PageSkeleton } from "@/components/ui";
import VoiceView from "./view";

export default function VoicePage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <VoiceView />
    </Suspense>
  );
}
