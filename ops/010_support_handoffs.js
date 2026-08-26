const target = db.getSiblingDB("gems");

const names = target.getCollectionNames();
if (names.indexOf("supportHandoffs") < 0) {
  target.createCollection("supportHandoffs");
}

target.runCommand({
  collMod: "supportHandoffs",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "userId", "question", "status", "createdAt"],
      properties: {
        _id: { bsonType: "string" },
        userId: { bsonType: "string" },
        question: { bsonType: "string", maxLength: 500 },
        reason: { bsonType: ["string", "null"], maxLength: 300 },
        transcript: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["role", "content"],
            properties: {
              role: { enum: ["user", "assistant"] },
              content: { bsonType: "string" },
            },
          },
        },
        status: { enum: ["open", "closed"] },
        createdAt: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
  validationAction: "error",
});

print("supportHandoffs ready");
