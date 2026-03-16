import { offerSchema } from "../lib/offers";

describe("offerSchema validation", () => {
  const validOffer = {
    vehicleId: "clxxx123",
    name: "Juan Pérez",
    email: "juan@example.com",
    phone: "+56912345678",
    offerAmount: 8500000,
    financing: false,
  };

  it("accepts a valid offer", () => {
    const result = offerSchema.safeParse(validOffer);
    expect(result.success).toBe(true);
  });

  it("rejects empty name", () => {
    const result = offerSchema.safeParse({ ...validOffer, name: "J" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toContain("name");
    }
  });

  it("rejects invalid email", () => {
    const result = offerSchema.safeParse({ ...validOffer, email: "not-an-email" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toContain("email");
    }
  });

  it("rejects phone that is too short", () => {
    const result = offerSchema.safeParse({ ...validOffer, phone: "123" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toContain("phone");
    }
  });

  it("rejects offer amount below 500000", () => {
    const result = offerSchema.safeParse({ ...validOffer, offerAmount: 100000 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toContain("offerAmount");
    }
  });

  it("rejects offer amount above 500000000", () => {
    const result = offerSchema.safeParse({ ...validOffer, offerAmount: 600000000 });
    expect(result.success).toBe(false);
  });

  it("accepts optional message", () => {
    const result = offerSchema.safeParse({ ...validOffer, message: "Me interesa el auto" });
    expect(result.success).toBe(true);
  });

  it("rejects message over 500 chars", () => {
    const result = offerSchema.safeParse({ ...validOffer, message: "x".repeat(501) });
    expect(result.success).toBe(false);
  });

  it("accepts financing = true", () => {
    const result = offerSchema.safeParse({ ...validOffer, financing: true });
    expect(result.success).toBe(true);
  });

  it("rejects missing vehicleId", () => {
    const { vehicleId: _, ...withoutId } = validOffer;
    const result = offerSchema.safeParse(withoutId);
    expect(result.success).toBe(false);
  });
});
