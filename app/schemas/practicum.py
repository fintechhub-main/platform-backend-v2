import uuid
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import date


class TaskCreate(BaseModel):
    team_id: uuid.UUID
    column: str = "todo"
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    tags: List[str] = []
    due_date: Optional[date] = None
    github: Optional[str] = None
    figma: Optional[str] = None
    assignees: List[Any] = []
    checklist: List[Any] = []
    comments: List[Any] = []
    activity: List[Any] = []


class TaskUpdate(BaseModel):
    column: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    tags: Optional[List[str]] = None
    due_date: Optional[date] = None
    github: Optional[str] = None
    figma: Optional[str] = None
    assignees: Optional[List[Any]] = None
    checklist: Optional[List[Any]] = None
    comments: Optional[List[Any]] = None
    activity: Optional[List[Any]] = None


class TaskOut(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    column: str
    title: str
    description: Optional[str]
    priority: str
    tags: List[str]
    due_date: Optional[date]
    github: Optional[str]
    figma: Optional[str]
    assignees: List[Any]
    checklist: List[Any]
    comments: List[Any]
    activity: List[Any]

    model_config = {"from_attributes": True}


class TeamCreate(BaseModel):
    name: str
    mentor: str
    deadline: Optional[date] = None
    progress: int = 0
    stack: List[str] = []
    links: dict = {}
    members: List[Any] = []
    branch_id: Optional[uuid.UUID] = None


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    mentor: Optional[str] = None
    deadline: Optional[date] = None
    progress: Optional[int] = None
    stack: Optional[List[str]] = None
    links: Optional[dict] = None
    members: Optional[List[Any]] = None
    branch_id: Optional[uuid.UUID] = None


class TeamOut(BaseModel):
    id: uuid.UUID
    name: str
    mentor: str
    deadline: Optional[date]
    progress: int
    stack: List[str]
    links: dict
    members: List[Any]
    branch_id: Optional[uuid.UUID]
    tasks: List[TaskOut] = []

    model_config = {"from_attributes": True}
