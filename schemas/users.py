from pydantic import BaseModel


class UserRequest(BaseModel):
    username: str
    password: str


class BioUpdate(BaseModel):
    bio: str


class PasswordUpdate(BaseModel):
    oldPassword: str
    newPassword: str
