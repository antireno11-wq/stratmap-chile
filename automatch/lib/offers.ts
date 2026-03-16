import { z } from "zod";
import { db } from "./db";
import type { Offer, OfferStatus } from "@prisma/client";

export const offerSchema = z.object({
  vehicleId: z.string().min(1, "Vehículo requerido"),
  listingId: z.string().optional(),
  name: z.string().min(2, "Nombre debe tener al menos 2 caracteres").max(100),
  email: z.string().email("Email inválido"),
  phone: z
    .string()
    .min(8, "Teléfono debe tener al menos 8 dígitos")
    .max(20)
    .regex(/^[+\d\s\-()]+$/, "Teléfono inválido"),
  offerAmount: z
    .number({ invalid_type_error: "Monto debe ser un número" })
    .int("Monto debe ser entero")
    .min(500000, "Monto mínimo $500.000")
    .max(500000000, "Monto demasiado alto"),
  financing: z.boolean().default(false),
  message: z.string().max(500, "Mensaje máximo 500 caracteres").optional(),
});

export type CreateOfferInput = z.infer<typeof offerSchema>;

export async function createOffer(input: CreateOfferInput): Promise<Offer> {
  const validated = offerSchema.parse(input);

  // Verify vehicle exists
  const vehicle = await db.vehicle.findUnique({
    where: { id: validated.vehicleId },
  });
  if (!vehicle) throw new Error("Vehículo no encontrado");

  return db.offer.create({
    data: {
      vehicleId: validated.vehicleId,
      listingId: validated.listingId ?? null,
      name: validated.name.trim(),
      email: validated.email.toLowerCase().trim(),
      phone: validated.phone.trim(),
      offerAmount: validated.offerAmount,
      financing: validated.financing,
      message: validated.message?.trim() ?? null,
      status: "NEW",
    },
  });
}

export async function updateOfferStatus(
  id: string,
  status: OfferStatus
): Promise<Offer> {
  return db.offer.update({
    where: { id },
    data: { status },
  });
}
