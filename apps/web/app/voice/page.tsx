import { Suspense } from "react";
import { Loading } from "@/components/ui";
import { VoiceView } from "./VoiceView";

export default function VoicePage() {
  return (
    <Suspense fallback={<Loading />}>
      <VoiceView />
    </Suspense>
  );
}
