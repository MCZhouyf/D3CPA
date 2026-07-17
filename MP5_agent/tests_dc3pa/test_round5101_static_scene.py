import numpy as np
import sys
from contextlib import nullcontext
from types import ModuleType, SimpleNamespace
from dc3pa.memory.mineclip_scene_encoder import (
 MineCLIPEncoderPolicy,MineCLIPStaticSceneEncoder,
 build_mineclip_image_encoder,build_mineclip_text_encoder,
 prepare_rgb_chw_uint8,prepare_static_video_numpy,l2_normalize
)

def test_single_scene_repeats_to_official_video_shape():
 image=np.zeros((160,256,3),dtype=np.uint8)
 frame=prepare_rgb_chw_uint8(image)
 video=prepare_static_video_numpy(image)
 assert frame.shape==(3,160,256)
 assert video.shape==(16,3,160,256)
 assert np.array_equal(video[0],video[-1])

def test_embedding_normalization():
 x=l2_normalize(np.array([3.0,4.0],dtype=np.float32))
 assert np.isclose(np.linalg.norm(x),1.0)

def test_text_encoder_tokenizes_with_official_clip_context(monkeypatch):
 observed={}
 class Tokens:
  def to(self,device): observed["device"]=device;return self
 class Features:
  def detach(self): return self
  def float(self): return self
  def cpu(self): return self
  def numpy(self): return np.ones((1,512),dtype=np.float32)
 class Model:
  def encode_text(self,tokens): observed["tokens"]=tokens;return Features()
 def tokenize(texts,max_length):
  observed["texts"]=texts;observed["max_length"]=max_length;return Tokens()
 torch=ModuleType("torch");torch.no_grad=nullcontext
 tokenization=ModuleType("mineclip.mineclip.tokenization")
 tokenization.tokenize_batch=tokenize
 monkeypatch.setitem(sys.modules,"torch",torch)
 monkeypatch.setitem(sys.modules,"mineclip",ModuleType("mineclip"))
 monkeypatch.setitem(sys.modules,"mineclip.mineclip",ModuleType("mineclip.mineclip"))
 monkeypatch.setitem(sys.modules,"mineclip.mineclip.tokenization",tokenization)
 encoder=MineCLIPStaticSceneEncoder(
  model=Model(),device="cuda",policy=MineCLIPEncoderPolicy()
 )
 result=encoder.encode_text("craft a pressure plate")
 assert observed["max_length"]==77
 assert observed["device"]=="cuda"
 assert observed["tokens"] is not None
 assert np.isclose(np.linalg.norm(result),1.0)

def test_builder_factories_match_plugin_loader_and_encoder_protocol(monkeypatch):
 class SceneEncoder:
  def encode_image(self,image): return ("image",image)
  def encode_text(self,text): return ("text",text)
 observed={}
 def load(config):
  observed.update(config);return SceneEncoder()
 monkeypatch.setattr(
  "dc3pa.memory.mineclip_scene_encoder._encoder_from_config",load
 )
 image=build_mineclip_image_encoder(checkpoint_path="checkpoint",device="cuda")
 text=build_mineclip_text_encoder(checkpoint_path="checkpoint",device="cuda")
 assert image.encode_image("pixels")==("image","pixels")
 assert text.encode_text("context")==("text","context")
 assert observed=={"checkpoint_path":"checkpoint","device":"cuda"}
