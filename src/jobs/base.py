"""Background job base class."""
from abc import ABC, abstractmethod
from telegram.ext import ContextTypes


class BackgroundJob(ABC):
    """Abstract base class for background jobs."""
    
    @abstractmethod
    async def run(self, context: ContextTypes.DEFAULT_TYPE):
        """Execute the background job."""
        pass
    
    @property
    @abstractmethod
    def interval_seconds(self) -> int:
        """Return the interval in seconds for this job."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this job."""
        pass
