"""MineCLIP[attn] static-scene image/text encoders for frozen memory.

MineCLIP is a video-language model. DC3PA Scene Exemplars contain one image
immediately before a high-level action. To preserve the approved single-image
memory semantics while using the official MineCLIP joint space, the image is
resized to 160×256 and repeated into a 16-frame static video. The official
MineCLIP[attn] checkpoint then produces a normalized 512-D video embedding.
Text is encoded by the same loaded MineCLIP model.

The encoder is pinned to the official MineDojo/MineCLIP repository commit and
the official attention-checkpoint MD5. The checkpoint itself remains external
and is additionally bound by SHA-256.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np


SCHEMA_VERSION = 1
OFFICIAL_REPOSITORY = "https://github.com/MineDojo/MineCLIP"
OFFICIAL_REPOSITORY_COMMIT = (
    "e6c06a0245fac63dceb38bc9bd4fecd033dae735"
)
OFFICIAL_VARIANT = "attn"
OFFICIAL_ATTN_CHECKPOINT_MD5 = "b5ece9198337cfd117a3bfbd921e56da"
OFFICIAL_POOL_TYPE = "attn.d2.nh8.glusw"
OFFICIAL_ARCH = "vit_base_p16_fz.v2.t2"
OFFICIAL_MLP_ADAPTER_SPEC = "v0-2.t0"
OFFICIAL_RESOLUTION = (160, 256)
OFFICIAL_FRAME_COUNT = 16
OFFICIAL_EMBEDDING_DIM = 512
FRAME_STRATEGY = "static_repeat_16"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def file_hash(path: str | Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_official_direct_url(payload: Mapping[str, Any]) -> str:
    """Return the pinned commit from pip's VCS provenance or fail closed."""

    url = str(payload.get("url", "")).rstrip("/").removesuffix(".git")
    expected_url = OFFICIAL_REPOSITORY.rstrip("/").removesuffix(".git")
    vcs_info = payload.get("vcs_info", {})
    if not isinstance(vcs_info, Mapping):
        raise ValueError("MineCLIP direct_url.json has no VCS provenance")
    commit = str(vcs_info.get("commit_id", "")).strip()
    if url != expected_url or vcs_info.get("vcs") != "git":
        raise ValueError("MineCLIP package is not installed from the official repository")
    if commit != OFFICIAL_REPOSITORY_COMMIT:
        raise ValueError("MineCLIP package commit does not match the pinned revision")
    return commit


def _verify_official_distribution(package_root: Path) -> dict[str, str]:
    distributions = importlib.metadata.packages_distributions().get("mineclip", ())
    if not distributions:
        distributions = ("mineclip",)
    direct_url = None
    for distribution_name in distributions:
        try:
            distribution = importlib.metadata.distribution(distribution_name)
        except importlib.metadata.PackageNotFoundError:
            continue
        raw = distribution.read_text("direct_url.json")
        if raw:
            direct_url = json.loads(raw)
            break
    if not isinstance(direct_url, Mapping):
        raise ValueError(
            "MineCLIP installation has no verifiable VCS direct_url.json"
        )
    commit = validate_official_direct_url(direct_url)
    digest = hashlib.sha256()
    for source in sorted(package_root.rglob("*.py")):
        relative = source.relative_to(package_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source.read_bytes())
        digest.update(b"\0")
    return {
        "mineclip_repository": OFFICIAL_REPOSITORY,
        "mineclip_repository_commit": commit,
        "mineclip_package_location_fingerprint": digest.hexdigest(),
    }


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    if not np.isfinite(norm) or norm <= 0:
        raise ValueError("MineCLIP embedding has invalid L2 norm")
    normalized = array / norm
    if not np.all(np.isfinite(normalized)):
        raise ValueError("MineCLIP embedding contains non-finite values")
    return normalized.astype(np.float32, copy=False)


def prepare_rgb_chw_uint8(
    image: np.ndarray,
    *,
    target_height: int = OFFICIAL_RESOLUTION[0],
    target_width: int = OFFICIAL_RESOLUTION[1],
) -> np.ndarray:
    """Convert one RGB image to CHW uint8 at MineCLIP resolution."""

    array = np.asarray(image)
    if array.ndim != 3:
        raise ValueError(f"Expected a 3-D image, got shape {array.shape}")
    if array.shape[0] == 3 and array.shape[-1] != 3:
        array = np.transpose(array, (1, 2, 0))
    if array.shape[-1] != 3:
        raise ValueError(f"Expected RGB channels, got shape {array.shape}")
    if array.dtype != np.uint8:
        if np.issubdtype(array.dtype, np.floating):
            maximum = float(np.nanmax(array)) if array.size else 0.0
            if maximum <= 1.0:
                array = np.rint(np.clip(array, 0.0, 1.0) * 255.0)
            else:
                array = np.rint(np.clip(array, 0.0, 255.0))
        else:
            array = np.clip(array, 0, 255)
        array = array.astype(np.uint8)

    height, width = array.shape[:2]
    if (height, width) != (target_height, target_width):
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError(
                "Pillow is required to resize MineCLIP scene images"
            ) from exc
        array = np.asarray(
            Image.fromarray(array, mode="RGB").resize(
                (target_width, target_height),
                resample=Image.Resampling.BILINEAR,
            ),
            dtype=np.uint8,
        )
    chw = np.transpose(array, (2, 0, 1))
    if chw.shape != (3, target_height, target_width):
        raise ValueError(f"Unexpected prepared image shape {chw.shape}")
    return np.ascontiguousarray(chw)


def prepare_static_video_numpy(image: np.ndarray) -> np.ndarray:
    frame = prepare_rgb_chw_uint8(image)
    video = np.repeat(
        frame[np.newaxis, ...],
        repeats=OFFICIAL_FRAME_COUNT,
        axis=0,
    )
    expected = (
        OFFICIAL_FRAME_COUNT,
        3,
        OFFICIAL_RESOLUTION[0],
        OFFICIAL_RESOLUTION[1],
    )
    if video.shape != expected:
        raise ValueError(f"Unexpected static-video shape {video.shape}")
    return np.ascontiguousarray(video)


@dataclass(frozen=True)
class MineCLIPEncoderPolicy:
    policy_name: str = "dc3pa-mineclip-attn-static-scene-v1"
    repository: str = OFFICIAL_REPOSITORY
    repository_commit: str = OFFICIAL_REPOSITORY_COMMIT
    variant: str = OFFICIAL_VARIANT
    architecture: str = OFFICIAL_ARCH
    pool_type: str = OFFICIAL_POOL_TYPE
    mlp_adapter_spec: str = OFFICIAL_MLP_ADAPTER_SPEC
    resolution: tuple[int, int] = OFFICIAL_RESOLUTION
    frame_count: int = OFFICIAL_FRAME_COUNT
    frame_strategy: str = FRAME_STRATEGY
    image_feature_dim: int = OFFICIAL_EMBEDDING_DIM
    hidden_dim: int = OFFICIAL_EMBEDDING_DIM
    output_dim: int = OFFICIAL_EMBEDDING_DIM
    official_checkpoint_md5: str = OFFICIAL_ATTN_CHECKPOINT_MD5
    l2_normalize_embeddings: bool = True
    single_image_scene_semantics_preserved: bool = True
    outcome_selected: bool = False
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    def __post_init__(self) -> None:
        if self.repository != OFFICIAL_REPOSITORY:
            raise ValueError("MineCLIP repository identity mismatch")
        if self.repository_commit != OFFICIAL_REPOSITORY_COMMIT:
            raise ValueError("MineCLIP repository commit mismatch")
        if self.variant != OFFICIAL_VARIANT:
            raise ValueError("Paper memory is pinned to MineCLIP[attn]")
        if self.architecture != OFFICIAL_ARCH:
            raise ValueError("MineCLIP architecture mismatch")
        if self.pool_type != OFFICIAL_POOL_TYPE:
            raise ValueError("MineCLIP attention pool mismatch")
        if self.mlp_adapter_spec != OFFICIAL_MLP_ADAPTER_SPEC:
            raise ValueError("MineCLIP adapter specification mismatch")
        if tuple(self.resolution) != OFFICIAL_RESOLUTION:
            raise ValueError("MineCLIP resolution mismatch")
        if self.frame_count != OFFICIAL_FRAME_COUNT:
            raise ValueError("MineCLIP static-scene frame count must be 16")
        if self.frame_strategy != FRAME_STRATEGY:
            raise ValueError("MineCLIP scene frame strategy mismatch")
        if (
            self.image_feature_dim,
            self.hidden_dim,
            self.output_dim,
        ) != (
            OFFICIAL_EMBEDDING_DIM,
            OFFICIAL_EMBEDDING_DIM,
            OFFICIAL_EMBEDDING_DIM,
        ):
            raise ValueError("MineCLIP embedding dimension mismatch")
        if self.official_checkpoint_md5 != OFFICIAL_ATTN_CHECKPOINT_MD5:
            raise ValueError("MineCLIP checkpoint MD5 mismatch")
        if not self.l2_normalize_embeddings:
            raise ValueError("MineCLIP retrieval embeddings must be normalized")
        if not self.single_image_scene_semantics_preserved:
            raise ValueError("Scene memory must retain single-image semantics")
        if self.outcome_selected:
            raise ValueError("MineCLIP profile cannot be selected from outcomes")
        expected = self.compute_policy_id()
        if self.policy_id and self.policy_id != expected:
            raise ValueError("MineCLIP policy hash mismatch")

    def model_kwargs(self) -> dict[str, Any]:
        return {
            "arch": self.architecture,
            "resolution": tuple(self.resolution),
            "pool_type": self.pool_type,
            "image_feature_dim": self.image_feature_dim,
            "mlp_adapter_spec": self.mlp_adapter_spec,
            "hidden_dim": self.hidden_dim,
        }

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("policy_id", None)
        payload["resolution"] = list(self.resolution)
        return payload

    def compute_policy_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "MineCLIPEncoderPolicy":
        return replace(self, policy_id=self.compute_policy_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.policy_id else self.with_id()
        payload = item.payload_without_id()
        payload["policy_id"] = item.policy_id
        return payload


@dataclass(frozen=True)
class MineCLIPCheckpointManifest:
    policy_id: str
    checkpoint_filename: str
    checkpoint_sha256: str
    checkpoint_md5: str
    checkpoint_size_bytes: int
    config_sha256: str
    torch_version: str
    mineclip_package_location_fingerprint: str
    mineclip_repository: str
    mineclip_repository_commit: str
    device_type: str
    dtype: str
    checkpoint_loaded_strictly: bool
    inference_probe_passed: bool
    image_embedding_dim: int
    text_embedding_dim: int
    image_embedding_shape: tuple[int, ...]
    text_embedding_shape: tuple[int, ...]
    image_embedding_l2_norm: float
    text_embedding_l2_norm: float
    deterministic_repeat_max_abs_diff: float
    deterministic_repeat_probe_passed: bool
    schema_version: int = SCHEMA_VERSION
    manifest_id: str = ""

    def __post_init__(self) -> None:
        required = (
            self.policy_id,
            self.checkpoint_filename,
            self.checkpoint_sha256,
            self.checkpoint_md5,
            self.config_sha256,
            self.torch_version,
            self.mineclip_package_location_fingerprint,
            self.mineclip_repository,
            self.mineclip_repository_commit,
            self.device_type,
            self.dtype,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("MineCLIP checkpoint manifest is incomplete")
        if self.checkpoint_md5 != OFFICIAL_ATTN_CHECKPOINT_MD5:
            raise ValueError("Checkpoint is not the official attn checkpoint")
        if self.mineclip_repository != OFFICIAL_REPOSITORY:
            raise ValueError("MineCLIP checkpoint probe repository mismatch")
        if self.mineclip_repository_commit != OFFICIAL_REPOSITORY_COMMIT:
            raise ValueError("MineCLIP checkpoint probe commit mismatch")
        if self.checkpoint_size_bytes <= 0:
            raise ValueError("Checkpoint size must be positive")
        if not all(
            (
                self.checkpoint_loaded_strictly,
                self.inference_probe_passed,
                self.deterministic_repeat_probe_passed,
            )
        ):
            raise ValueError("MineCLIP checkpoint/probe validation is incomplete")
        if (
            self.image_embedding_dim,
            self.text_embedding_dim,
        ) != (
            OFFICIAL_EMBEDDING_DIM,
            OFFICIAL_EMBEDDING_DIM,
        ):
            raise ValueError("MineCLIP probe dimension mismatch")
        if tuple(self.image_embedding_shape) != (OFFICIAL_EMBEDDING_DIM,):
            raise ValueError("MineCLIP image probe shape mismatch")
        if tuple(self.text_embedding_shape) != (OFFICIAL_EMBEDDING_DIM,):
            raise ValueError("MineCLIP text probe shape mismatch")
        if not np.isclose(self.image_embedding_l2_norm, 1.0, atol=1e-5):
            raise ValueError("MineCLIP image probe is not L2-normalized")
        if not np.isclose(self.text_embedding_l2_norm, 1.0, atol=1e-5):
            raise ValueError("MineCLIP text probe is not L2-normalized")
        if self.deterministic_repeat_max_abs_diff < 0:
            raise ValueError("MineCLIP determinism delta is invalid")
        expected = self.compute_manifest_id()
        if self.manifest_id and self.manifest_id != expected:
            raise ValueError("MineCLIP checkpoint manifest hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("manifest_id", None)
        return payload

    def compute_manifest_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "MineCLIPCheckpointManifest":
        return replace(self, manifest_id=self.compute_manifest_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.manifest_id else self.with_id()
        payload = item.payload_without_id()
        payload["manifest_id"] = item.manifest_id
        return payload


class MineCLIPStaticSceneEncoder:
    """Image/text encoders backed by one official MineCLIP model instance."""

    def __init__(
        self,
        *,
        model: Any,
        device: Any,
        policy: MineCLIPEncoderPolicy,
    ) -> None:
        self.model = model
        self.device = device
        self.policy = policy if policy.policy_id else policy.with_id()

    def encode_image(self, image: np.ndarray) -> np.ndarray:
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("PyTorch is required for MineCLIP inference") from exc
        video = prepare_static_video_numpy(image)
        tensor = torch.from_numpy(video).unsqueeze(0).to(self.device)
        with torch.no_grad():
            features = self.model.encode_video(tensor)
        array = features.detach().float().cpu().numpy()
        if array.shape != (1, OFFICIAL_EMBEDDING_DIM):
            raise ValueError(f"Unexpected MineCLIP image embedding shape {array.shape}")
        return l2_normalize(array[0])

    def encode_text(self, text: str) -> np.ndarray:
        if not str(text).strip():
            raise ValueError("MineCLIP text cannot be empty")
        try:
            import torch
            from mineclip.mineclip.tokenization import tokenize_batch
        except ImportError as exc:
            raise RuntimeError("PyTorch is required for MineCLIP inference") from exc
        tokens = tokenize_batch([str(text)], max_length=77).to(self.device)
        with torch.no_grad():
            features = self.model.encode_text(tokens)
        array = features.detach().float().cpu().numpy()
        if array.shape != (1, OFFICIAL_EMBEDDING_DIM):
            raise ValueError(f"Unexpected MineCLIP text embedding shape {array.shape}")
        return l2_normalize(array[0])


def load_official_model(
    *,
    checkpoint_path: str | Path,
    policy: Optional[MineCLIPEncoderPolicy] = None,
    device: Optional[str] = None,
) -> tuple[MineCLIPStaticSceneEncoder, dict[str, Any]]:
    policy = policy or MineCLIPEncoderPolicy()
    policy = policy if policy.policy_id else policy.with_id()
    path = Path(checkpoint_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    md5 = file_hash(path, "md5")
    if md5 != policy.official_checkpoint_md5:
        raise ValueError(
            f"MineCLIP checkpoint MD5 mismatch: {md5} != "
            f"{policy.official_checkpoint_md5}"
        )
    try:
        import torch
        import mineclip
        from mineclip import MineCLIP
    except ImportError as exc:
        raise RuntimeError(
            "Install the official MineDojo/MineCLIP package before loading"
        ) from exc

    resolved_device = torch.device(
        device or ("cuda" if torch.cuda.is_available() else "cpu")
    )
    model = MineCLIP(**policy.model_kwargs()).to(resolved_device)
    model.load_ckpt(str(path), strict=True)
    model.eval()
    package_path = Path(mineclip.__file__).resolve()
    package_identity = _verify_official_distribution(package_path.parent)
    metadata = {
        "torch_version": str(torch.__version__),
        "mineclip_package_path": str(package_path),
        **package_identity,
        "device_type": str(resolved_device.type),
        "checkpoint_sha256": file_hash(path, "sha256"),
        "checkpoint_md5": md5,
        "checkpoint_size_bytes": path.stat().st_size,
    }
    return (
        MineCLIPStaticSceneEncoder(
            model=model,
            device=resolved_device,
            policy=policy,
        ),
        metadata,
    )


class MineCLIPImageEncoder:
    def __init__(self, scene_encoder: MineCLIPStaticSceneEncoder):
        self.scene_encoder = scene_encoder

    def encode(self, image: np.ndarray) -> np.ndarray:
        return self.scene_encoder.encode_image(image)


class MineCLIPTextEncoder:
    def __init__(self, scene_encoder: MineCLIPStaticSceneEncoder):
        self.scene_encoder = scene_encoder

    def encode(self, text: str) -> np.ndarray:
        return self.scene_encoder.encode_text(text)


_MODEL_CACHE: dict[str, MineCLIPStaticSceneEncoder] = {}


def _encoder_from_config(config: Mapping[str, Any]) -> MineCLIPStaticSceneEncoder:
    checkpoint_path = str(config.get("checkpoint_path", "")).strip()
    if not checkpoint_path:
        raise ValueError("MineCLIP checkpoint_path is required")
    device = config.get("device")
    cache_key = _sha(
        {
            "checkpoint_path": str(Path(checkpoint_path).resolve()),
            "device": device,
            "policy": MineCLIPEncoderPolicy().to_dict(),
        }
    )
    if cache_key not in _MODEL_CACHE:
        encoder, _ = load_official_model(
            checkpoint_path=checkpoint_path,
            device=str(device) if device else None,
        )
        _MODEL_CACHE[cache_key] = encoder
    return _MODEL_CACHE[cache_key]


def build_mineclip_image_encoder(config: Mapping[str, Any]) -> MineCLIPImageEncoder:
    return MineCLIPImageEncoder(_encoder_from_config(config))


def build_mineclip_text_encoder(config: Mapping[str, Any]) -> MineCLIPTextEncoder:
    return MineCLIPTextEncoder(_encoder_from_config(config))
