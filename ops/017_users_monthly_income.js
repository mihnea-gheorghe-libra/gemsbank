const target = db.getSiblingDB("gems");

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
        "fullName",
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
        fullName: { bsonType: "string" },
        passwordHash: { bsonType: "string" },
        pinHash: { bsonType: "string" },
        pinEncrypted: { bsonType: ["string", "null"] },
        kycCaseId: { bsonType: "string" },
        prefs: { bsonType: "object" },
        signIn: { bsonType: "object" },
        pin: { bsonType: "object" },
        password: { bsonType: "object" },
        status: { enum: ["active", "suspended", "locked"] },
        createdAt: { bsonType: "date" },
        monthlyIncomeMinorUnits: { bsonType: ["int", "long", "null"] },
      },
    },
  },
  validationLevel: "moderate",
});

print("017_users_monthly_income applied — users now also accepts monthlyIncomeMinorUnits.");
