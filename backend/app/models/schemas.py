from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)


class AssignmentCreate(BaseModel):
    courseId: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=10000)
    dueAt: datetime
    maxMarks: int = Field(ge=1, le=10000)
    allowedTypes: list[str] = Field(default_factory=lambda: ["pdf", "docx", "txt", "zip", "png", "jpg", "jpeg"])
    maxFileSizeMB: int = Field(default=16, ge=1, le=100)
    allowResubmission: bool = True

    @field_validator("allowedTypes")
    @classmethod
    def normalize_extensions(cls, values):
        normalized = sorted({value.strip().lower().lstrip(".") for value in values if value.strip()})
        if not normalized or any(value not in {"pdf", "doc", "docx", "txt", "zip", "png", "jpg", "jpeg"} for value in normalized):
            raise ValueError("allowedTypes must contain supported file extensions")
        return normalized

    @field_validator("dueAt")
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError("dueAt must include a timezone")
        return value


class GradeInput(BaseModel):
    marks: int = Field(ge=0)
    feedback: str = Field(default="", max_length=5000)
