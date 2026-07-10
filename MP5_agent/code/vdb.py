from langchain.vectorstores import Chroma
from langchain.embeddings.openai import OpenAIEmbeddings
from PIL import Image
import numpy as np
import os
import cv2
from MINECLIP import load as load_mineclip
import torch
import json
from scipy.spatial.distance import cosine

os.environ["OPENAI_API_KEY"]= 'sk-yby7EXO2V6fMUo4sCc9749A1F64e4d5fB99c3484A49d332d'
vdb = Chroma(collection_name="test",
             embedding_function=OpenAIEmbeddings(openai_api_base="https://api.xiaoai.plus/v1"),
             persist_directory='testdb')

tasks = [
    {"task_name": "Task 1", "plan": "Plan for Task 1", "tips": "Tips for Task 1", "image_path": "apple_s_000022.png"},
    {"task_name": "Task 2", "plan": "Plan for Task 2", "tips": "Tips for Task 2", "image_path": "bicycle_s_000017.png"}
    ]

encoder_ckpt_path = 'model_zoo/mineclip_ckpt/mineclip_image_encoder_vit-B_196tokens.pth'
device = torch.device("cuda")
num_vision_token = 196
vision_hidden_size = 768

visual_encoder, visual_preprocess = load_mineclip(encoder_ckpt_path=encoder_ckpt_path, device=device)
visual_encoder.to(device)


for name, param in visual_encoder.named_parameters():
    param.requires_grad = False
visual_encoder.eval()

def load_and_transform_image_data_clip(image_path):
    image = Image.open(image_path)
    image_output = visual_preprocess(image).to(device)  # 3 x 224 x 224
    image_output = image_output.unsqueeze(0)
    return image_output  # 1 x 3 x 224 x 224

def clip_encode_image(inputs):
    with torch.no_grad():
        embeddings = visual_encoder.forward_patch_features(inputs)[
            :, : num_vision_token
        ]  # bsz x self.num_vision_token x 1024
        image_embeds = embeddings.reshape(-1, vision_hidden_size).to(
            torch.float32
        )  # bsz*num vision token x 1024
    return image_embeds
    
def encode_image(image_path):
    inputs = load_and_transform_image_data_clip(image_path)
    inputs = inputs.to(torch.float32)
    inputs_llama = clip_encode_image(inputs)
    return inputs_llama


for task in tasks:
    embedding = encode_image(task["image_path"]).cpu().numpy()
    embedding_list = embedding.tolist()
    embedding_json = json.dumps(embedding_list)
    vdb.add_texts(
        ids=[task["task_name"]],
        texts=[task["plan"]],
        metadatas=[{"task_name": task["task_name"], "plan": task["plan"], 
        "tips": task["tips"], "embedding_shape": str(embedding.shape), "embedding_dtype": str(embedding.dtype), "embedding": embedding_json}]
    )

def retrieve_top_k_by_task_name(vdb, task_name, k=3):
    results = vdb.similarity_search(task_name, k=k)
    tasks = [result for result in results]
    return tasks

def calculate_cosine_similarity(embedding1, embedding2):
    vec1 = embedding1.flatten()
    vec2 = embedding2.flatten()
    similarity = 1 - cosine(vec1, vec2)
    return similarity

def find_most_similar_image(target_image_path, results):
    max_similarity = -1
    most_similar_task = None
    target_embedding = encode_image(target_image_path).cpu().numpy()

    for item in results:
        candidate_embedding = json.loads(item.metadata["embedding"])
        candidate_embedding = np.array(candidate_embedding)
        similarity = calculate_cosine_similarity(target_embedding, candidate_embedding)

        if similarity > max_similarity:
            max_similarity = similarity
            most_similar_task = item.metadata

    return most_similar_task

top_k_tasks = retrieve_top_k_by_task_name(vdb, "Task", k=3)
target_image_path = 'apple_s_000027.png'
most_similar_task = find_most_similar_image(target_image_path, top_k_tasks)
if most_similar_task:
    print("Most similar task based on image:", most_similar_task['task_name'])
