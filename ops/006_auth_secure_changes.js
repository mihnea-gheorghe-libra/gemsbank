const target = db.getSiblingDB("gems");

target.runCommand({
  collMod: "recoveryCases",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "userId", "kind", "status", "createdAt", "updatedAt"],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        kind: { enum: ["password_reset", "email_change", "phone_change", "pin_change"] },
        status: { enum: ["code_sent", "code_verified", "completed"] },
        otp: {
          bsonType: ["object", "null"],
          required: ["codeHash", "expiresAt", "sentAt", "attempts"],
          properties: {
            codeHash: { bsonType: "string" },
            expiresAt: { bsonType: "date" },
            sentAt: { bsonType: "date" },
            attempts: { bsonType: "int" },
          },
        },
        payload: { bsonType: "object" },
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

target.runCommand({
  collMod: "sessions",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "userId", "tokenHash", "issuedAt", "expiresAt"],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        tokenHash: { bsonType: "string" },
        issuedAt: { bsonType: "date" },
        expiresAt: { bsonType: "date" },
        revokedAt: { bsonType: ["date", "null"] },
        userAgent: { bsonType: ["string", "null"] },
        ipAddress: { bsonType: ["string", "null"] },
      },
    },
  },
  validationLevel: "moderate",
});

const withoutPhone = target.users.countDocuments({ phone: { $exists: false } });

print(
  "006_auth_secure_changes applied — recoveryCases now accepts email_change/phone_change/" +
    "pin_change, sessions record userAgent/ipAddress. " +
    withoutPhone +
    " user(s) have no phone on file."
);
