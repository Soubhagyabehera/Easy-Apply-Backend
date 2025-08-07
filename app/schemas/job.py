from pydantic import BaseModel
from typing import List, Optional

class JobBase(BaseModel):
    title: str
    company: str
    location: str
    description: str
    requirements: List[str]
    salary_range: Optional[str] = None
    apply_url: Optional[str] = None
    posted_date: Optional[str] = None
    # Government job specific fields
    organization: Optional[str] = None
    career_url: Optional[str] = None
    last_date: Optional[str] = None
    job_type: Optional[str] = "Government"
    department: Optional[str] = None
    experience_required: Optional[str] = None

class JobCreate(JobBase):
    pass

class JobUpdate(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[List[str]] = None
    salary_range: Optional[str] = None
    apply_url: Optional[str] = None
    posted_date: Optional[str] = None
    # Government job specific fields
    organization: Optional[str] = None
    career_url: Optional[str] = None
    last_date: Optional[str] = None
    job_type: Optional[str] = None
    department: Optional[str] = None
    experience_required: Optional[str] = None
    is_active: Optional[bool] = None

class Job(JobBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True
