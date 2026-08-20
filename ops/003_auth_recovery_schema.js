const target = db.getSiblingDB("gems");

target.users.updateMany(
  { signIn: { $exists: false } },
  { $set: { signIn: { failures: 0, lockedUntil: null } } }
);

const withoutPin = target.users.countDocuments({ pinEncrypted: { $exists: false } });

target.runCommand({
  collMod: "users",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id",
        "username",
        "email",
        "phone",
        "passwordHash",
        "pinHash",
        "kycCaseId",
        "status",
        "createdAt",
      ],
      properties: {
        _id: { bsonType: "string" },
        username: { bsonType: "string" },
        email: { bsonType: "string" },
        phone: { bsonType: "string" },
        passwordHash: { bsonType: "string" },
        pinHash: { bsonType: "string" },
        pinEncrypted: { bsonType: ["string", "null"] },
        kycCaseId: { bsonType: "string" },
        prefs: { bsonType: "object" },
        signIn: {
          bsonType: "object",
          required: ["failures", "lockedUntil"],
          properties: {
            failures: { bsonType: "int" },
            lockedUntil: { bsonType: ["date", "null"] },
          },
        },
        status: { enum: ["active", "suspended"] },
        createdAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

target.createCollection("recoveryCases");

target.runCommand({
  collMod: "recoveryCases",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "userId", "kind", "status", "createdAt", "updatedAt"],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        kind: { enum: ["password_reset"] },
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
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

print(
  "003_auth_recovery_schema applied — " +
    withoutPin +
    " user(s) have no pinEncrypted and cannot use PIN recovery"
);
