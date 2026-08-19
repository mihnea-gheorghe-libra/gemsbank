from pydantic import BaseModel, Field


class ContactRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    phone: str = Field(min_length=6, max_length=25)


class VerifyCodeRequest(BaseModel):
    code: str = Field(min_length=4, max_length=8)


class CredentialsRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=200)
    pin: str = Field(min_length=4, max_length=8)
    pin_confirmation: str = Field(min_length=4, max_length=8, alias="pinConfirmation")

    model_config = {"populate_by_name": True}
