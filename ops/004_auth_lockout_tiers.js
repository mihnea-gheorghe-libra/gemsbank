const target = db.getSiblingDB("gems");

target.users.updateMany(
  {},
  {
    $set: {
      pin: { failures: 0, locked: false },
      password: { failures: 0, lockoutStage: 0, lockedUntil: null },
    },
    $unset: { signIn: "" },
  }
);

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
        pin: {
          bsonType: "object",
          required: ["failures", "locked"],
          properties: {
            failures: { bsonType: "int" },
            locked: { bsonType: "bool" },
          },
        },
        password: {
          bsonType: "object",
          required: ["failures", "lockoutStage", "lockedUntil"],
          properties: {
            failures: { bsonType: "int" },
            lockoutStage: { bsonType: "int" },
            lockedUntil: { bsonType: ["date", "null"] },
          },
        },
        status: { enum: ["active", "suspended", "locked"] },
        createdAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

print("004_auth_lockout_tiers applied — signIn split into pin/password lockout tracks");
