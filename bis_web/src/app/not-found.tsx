import Link from "next/link";
import { Compass } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";

export default function NotFound() {
  return (
    <EmptyState
      icon={Compass}
      title="That page does not exist"
      hint="The pages here are Home, Search, Tender Analysis, Compliance, Standards and Dashboard."
      action={
        <Button asChild>
          <Link href="/">Back to search</Link>
        </Button>
      }
    />
  );
}
