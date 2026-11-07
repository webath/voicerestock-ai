import { Suspense } from "react";
import { Loading } from "@/components/ui";
import { CustomerView } from "./CustomerView";

// Owner: Δημήτρης. Σελίδα πελάτη: ιστορικό, πρόβλεψη ανά είδος, πρόταση παραγγελίας, εξήγηση.
export default function CustomerPage({ params }: PageProps<"/customers/[trdr]">) {
  return (
    <Suspense fallback={<Loading />}>
      <Customer params={params} />
    </Suspense>
  );
}

async function Customer({ params }: Pick<PageProps<"/customers/[trdr]">, "params">) {
  const { trdr } = await params;
  return <CustomerView trdr={Number(trdr)} />;
}
