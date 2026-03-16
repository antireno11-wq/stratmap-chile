"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { formatCLP } from "@/lib/utils";

const schema = z.object({
  name: z.string().min(2, "Mínimo 2 caracteres").max(100),
  email: z.string().email("Email inválido"),
  phone: z
    .string()
    .min(8, "Mínimo 8 dígitos")
    .max(20)
    .regex(/^[+\d\s\-()]+$/, "Solo números y símbolos válidos"),
  offerAmount: z
    .string()
    .refine((v) => /^\d+$/.test(v.replace(/\./g, "")), "Ingresa un monto válido")
    .refine(
      (v) => parseInt(v.replace(/\./g, "")) >= 500000,
      "Monto mínimo $500.000"
    ),
  financing: z.boolean().default(false),
  message: z.string().max(500, "Máximo 500 caracteres").optional(),
});

type FormValues = z.infer<typeof schema>;

interface OfferFormProps {
  vehicleId: string;
  listingId: string;
  listedPrice: number;
}

export function OfferForm({ vehicleId, listingId, listedPrice }: OfferFormProps) {
  const [sent, setSent] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      offerAmount: listedPrice.toString(),
      financing: false,
    },
  });

  const offerAmountRaw = watch("offerAmount") ?? "";
  const parsed = parseInt(offerAmountRaw.replace(/\./g, "")) || 0;
  const diff = parsed - listedPrice;

  const onSubmit = async (data: FormValues) => {
    setServerError(null);
    try {
      const res = await fetch("/api/offers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          vehicleId,
          listingId,
          name: data.name,
          email: data.email,
          phone: data.phone,
          offerAmount: parseInt(data.offerAmount.replace(/\./g, "")),
          financing: data.financing,
          message: data.message,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: "Error al enviar oferta" }));
        throw new Error(err.error ?? "Error al enviar oferta");
      }

      setSent(true);
    } catch (e: unknown) {
      setServerError(e instanceof Error ? e.message : "Error inesperado");
    }
  };

  if (sent) {
    return (
      <div className="text-center py-8 space-y-3">
        <div className="w-14 h-14 bg-emerald-100 rounded-full flex items-center justify-center mx-auto">
          <svg className="w-7 h-7 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h3 className="font-semibold text-slate-900">¡Oferta enviada!</h3>
        <p className="text-sm text-slate-600">
          Nos pondremos en contacto contigo a la brevedad.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <Input
        label="Nombre completo"
        placeholder="Juan Pérez"
        error={errors.name?.message}
        {...register("name")}
      />
      <Input
        label="Email"
        type="email"
        placeholder="juan@email.com"
        error={errors.email?.message}
        {...register("email")}
      />
      <Input
        label="Teléfono"
        placeholder="+56 9 1234 5678"
        error={errors.phone?.message}
        {...register("phone")}
      />

      {/* Offer amount */}
      <div className="space-y-1">
        <label className="text-sm font-medium text-slate-700">Monto ofertado (CLP)</label>
        <input
          type="text"
          placeholder="Ej: 8500000"
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          {...register("offerAmount")}
        />
        {errors.offerAmount && (
          <p className="text-xs text-red-600">{errors.offerAmount.message}</p>
        )}
        {parsed > 0 && (
          <p className={`text-xs font-medium ${diff < 0 ? "text-blue-600" : diff > 0 ? "text-slate-500" : "text-slate-500"}`}>
            {diff === 0
              ? "Igual al precio publicado"
              : diff < 0
              ? `${formatCLP(Math.abs(diff))} bajo el precio publicado`
              : `${formatCLP(diff)} sobre el precio publicado`}
          </p>
        )}
      </div>

      {/* Financing */}
      <label className="flex items-center gap-3 cursor-pointer">
        <input
          type="checkbox"
          className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
          {...register("financing")}
        />
        <span className="text-sm text-slate-700">Requiero financiamiento</span>
      </label>

      {/* Message */}
      <div className="space-y-1">
        <label className="text-sm font-medium text-slate-700">Mensaje (opcional)</label>
        <textarea
          rows={3}
          placeholder="Cuéntanos algo más sobre tu oferta o preferencias..."
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
          {...register("message")}
        />
        {errors.message && (
          <p className="text-xs text-red-600">{errors.message.message}</p>
        )}
      </div>

      {serverError && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg">
          {serverError}
        </div>
      )}

      <Button
        type="submit"
        size="lg"
        loading={isSubmitting}
        className="w-full"
      >
        Enviar oferta
      </Button>

      <p className="text-xs text-slate-500 text-center">
        Tu información es confidencial y solo se usará para contactarte.
      </p>
    </form>
  );
}
