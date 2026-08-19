const target = db.getSiblingDB("gems");

target.runCommand({
  collMod: "kycCases",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "status", "createdAt", "updatedAt"],
      properties: {
        _id: { bsonType: "string" },
        status: {
          enum: [
            "started",
            "document_submitted",
            "contact_provided",
            "code_verified",
            "completed",
          ],
        },
        document: {
          bsonType: ["object", "null"],
          required: ["docRef", "docType", "extracted", "submittedAt"],
          properties: {
            docRef: { bsonType: "string" },
            docType: { bsonType: "string" },
            submittedAt: { bsonType: "date" },
            extracted: {
              bsonType: "object",
              required: ["fullName", "cnpMasked", "documentNumberMasked", "expiresOn"],
              properties: {
                fullName: { bsonType: "string" },
                cnpMasked: { bsonType: "string" },
                documentNumberMasked: { bsonType: "string" },
                expiresOn: { bsonType: "string" },
              },
            },
          },
        },
        contact: {
          bsonType: ["object", "null"],
          required: ["email", "phone"],
          properties: {
            email: { bsonType: "string" },
            phone: { bsonType: "string" },
          },
        },
        otp: {
          bsonType: ["object", "null"],
          required: ["codeHash", "expiresAt", "sentAt", "attempts", "resends"],
          properties: {
            codeHash: { bsonType: "string" },
            expiresAt: { bsonType: "date" },
            sentAt: { bsonType: "date" },
            attempts: { bsonType: "int" },
            resends: { bsonType: "int" },
          },
        },
        userId: { bsonType: ["string", "null"] },
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

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
        kycCaseId: { bsonType: "string" },
        prefs: { bsonType: "object" },
        status: { enum: ["active", "suspended"] },
        createdAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
});

print("001_onboarding_kyc_schema applied");
