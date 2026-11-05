"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { PROPERTY_TYPES } from "@/lib/format";
import { useTeam } from "@/lib/hooks";
import type { Property } from "@/lib/types";
import { Button, ErrorText, Field, Input, Select, Textarea } from "./ui";

export function PropertyForm({ property }: { property?: Property }) {
  const router = useRouter();
  const qc = useQueryClient();
  const team = useTeam();
  const [amenities, setAmenities] = useState(property?.amenities.join(", ") ?? "");
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      property
        ? api<Property>(`/properties/${property.id}`, { method: "PATCH", json: body })
        : api<Property>("/properties", { method: "POST", json: body }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["properties"] });
      qc.setQueryData(["property", p.id], p);
      if (!property) router.replace(`/dashboard/properties/${p.id}`);
    },
  });

  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        const num = (k: string) => (f.get(k) === "" ? null : f.get(k));
        save.mutate({
          title: f.get("title"), description: f.get("description"),
          listing_type: f.get("listing_type"), property_type: f.get("property_type"),
          status: f.get("status"), price: num("price"), area_sqft: num("area_sqft"),
          bedrooms: num("bedrooms"), bathrooms: num("bathrooms"),
          city: f.get("city") || null, locality: f.get("locality") || null,
          address: f.get("address") || null, published: f.get("published") === "on",
          assigned_to: f.get("assigned_to") || null,
          amenities: amenities.split(",").map((a) => a.trim()).filter(Boolean),
        });
      }}
    >
      <Field label="Title"><Input name="title" required minLength={3} defaultValue={property?.title} placeholder="3BHK lake-facing apartment" /></Field>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="For">
          <Select name="listing_type" defaultValue={property?.listing_type ?? "sale"}>
            <option value="sale">Sale</option><option value="rent">Rent</option>
          </Select>
        </Field>
        <Field label="Type">
          <Select name="property_type" defaultValue={property?.property_type ?? "apartment"}>
            {PROPERTY_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </Select>
        </Field>
        <Field label="Status">
          <Select name="status" defaultValue={property?.status ?? "available"}>
            <option value="draft">Draft</option><option value="available">Available</option>
            <option value="under_offer">Under offer</option><option value="sold">Sold</option>
            <option value="rented">Rented</option>
          </Select>
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-4">
        <Field label="Price (₹)" hint="Monthly rent for rentals"><Input name="price" type="number" min={0} defaultValue={property?.price ?? ""} /></Field>
        <Field label="Area (sq ft)"><Input name="area_sqft" type="number" min={0} defaultValue={property?.area_sqft ?? ""} /></Field>
        <Field label="Bedrooms"><Input name="bedrooms" type="number" min={0} defaultValue={property?.bedrooms ?? ""} /></Field>
        <Field label="Bathrooms"><Input name="bathrooms" type="number" min={0} defaultValue={property?.bathrooms ?? ""} /></Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Locality"><Input name="locality" defaultValue={property?.locality ?? ""} placeholder="Hebbal" /></Field>
        <Field label="City"><Input name="city" defaultValue={property?.city ?? ""} placeholder="Bengaluru" /></Field>
      </div>
      <Field label="Address" hint="Used as the meeting point for site visits"><Input name="address" defaultValue={property?.address ?? ""} /></Field>
      <Field label="Amenities" hint="Comma separated">
        <Input value={amenities} onChange={(e) => setAmenities(e.target.value)} placeholder="gym, pool, covered parking" />
      </Field>
      <Field label="Description" hint="The assistant quotes from this. Include possession date, floor, facing, parking.">
        <Textarea name="description" rows={6} defaultValue={property?.description} />
      </Field>
      <Field label="Responsible agent">
        <Select name="assigned_to" defaultValue={property?.assigned_to ?? ""}>
          <option value="">Anyone</option>
          {team.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
        </Select>
      </Field>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" name="published" defaultChecked={property?.published ?? true} className="mt-0.5" />
        <span>Show on my listing page and let the WhatsApp assistant offer it</span>
      </label>
      <ErrorText error={save.error} />
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={save.isPending}>{property ? "Save changes" : "Add property"}</Button>
        {save.isSuccess && property && <span className="text-sm text-registry">Saved</span>}
      </div>
    </form>
  );
}
