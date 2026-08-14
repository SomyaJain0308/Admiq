# All model classes must be imported here so SQLAlchemy's declarative class registry has every mapped class available before mapper configuration runs. Several models reference each other via string-based relationship()/primaryjoin (to avoid circular imports between model files) - those string references are only resolvable if the referenced class has actually been imported *somewhere* in the running process by the time SQLAlchemy configures mappers. Individual files importing each other under `if TYPE_CHECKING:` doesn't count - that's a no-op at runtime. This module is the single place that guarantees all of them are really imported, and it gets pulled in from database.py so both the FastAPI app and the Celery worker always have the full registry populated.

from backend.app.models.College import College
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff, StaffCollege
from backend.app.models.WhatsappNumber import WhatsAppNumber
from backend.app.models.Student import Student
from backend.app.models.StudentSession import StudentSession
from backend.app.models.Message import Message
from backend.app.models.Document import Document
from backend.app.models.Chunk import Chunk
from backend.app.models.LowConfidenceQuery import LowConfidenceQuery