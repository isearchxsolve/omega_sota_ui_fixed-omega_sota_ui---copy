"""
OMEGA Hardware Tier Detection
Detects system capabilities to adjust model precision, VRAM limits, and batch sizes.
"""
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class HardwareTier(Enum):
    LOW_TIER = "low_tier"       # < 8GB VRAM (CPU only, or small GPU)
    MID_TIER = "mid_tier"       # 8GB - 16GB VRAM (e.g., RTX 3060/4060, T4)
    HIGH_TIER = "high_tier"     # 16GB - 40GB VRAM (e.g., RTX 3090, A10g)
    ULTRA_TIER = "ultra_tier"   # > 40GB VRAM (e.g., A100, H100)

@dataclass
class HardwareProfile:
    tier: HardwareTier
    total_vram_gb: float
    gpu_count: int
    has_cuda: bool
    recommended_quantization: str

class HardwareDetector:
    @staticmethod
    def detect_hardware() -> HardwareProfile:
        """Detect GPU capabilities safely with graceful fallbacks."""
        total_vram_gb = 0.0
        gpu_count = 0
        has_cuda = False
        
        try:
            import torch
            if torch.cuda.is_available():
                has_cuda = True
                gpu_count = torch.cuda.device_count()
                # Aggregate VRAM across available GPUs
                for i in range(gpu_count):
                    vram_bytes = torch.cuda.get_device_properties(i).total_memory
                    total_vram_gb += vram_bytes / (1024 ** 3)
        except ImportError:
            logger.warning("PyTorch not found. Defaulting to CPU-only hardware profile.")
        except Exception as e:
            logger.error(f"Error detecting hardware: {e}")

        # Determine Tier
        if not has_cuda or total_vram_gb < 8.0:
            tier = HardwareTier.LOW_TIER
            quantization = "4bit"
        elif total_vram_gb < 16.0:
            tier = HardwareTier.MID_TIER
            quantization = "8bit"
        elif total_vram_gb < 40.0:
            tier = HardwareTier.HIGH_TIER
            quantization = "16bit"
        else:
            tier = HardwareTier.ULTRA_TIER
            quantization = "none"

        profile = HardwareProfile(
            tier=tier,
            total_vram_gb=round(total_vram_gb, 2),
            gpu_count=gpu_count,
            has_cuda=has_cuda,
            recommended_quantization=quantization
        )
        
        logger.info(f"Hardware Profile Detected: {tier.value} | {profile.total_vram_gb}GB VRAM | Quantization: {quantization}")
        return profile