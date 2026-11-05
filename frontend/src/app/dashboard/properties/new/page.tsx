import { PropertyForm } from "@/components/property-form";
import { PageHeader } from "@/components/ui";

export default function NewPropertyPage() {
  return (
    <div className="max-w-3xl">
      <PageHeader title="Add property" subtitle="You can add photos and brochures after saving." />
      <PropertyForm />
    </div>
  );
}
