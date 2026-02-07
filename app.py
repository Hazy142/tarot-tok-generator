import streamlit as st
from moviepy import *
from moviepy.video.fx import Margin, Resize
from moviepy.audio.fx import AudioFadeOut
import tempfile
import os
from PIL import Image, ImageOps
import numpy as np

# --- CONFIG & VIBE ---
TIKTOK_SIZE = (1080, 1920)
FPS = 30

st.set_page_config(page_title="Tarot-Tok Generator", layout="wide", page_icon="🔮")

# --- CSS FOR NEON VIBE ---
st.markdown("""
    <style>
    .stApp {
        background-color: #0e1117;
        color: #00ffcc;
    }
    .stButton>button {
        background-color: #2b2b2b;
        color: #00ffcc;
        border: 1px solid #00ffcc;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🔮 Soul Algorithm: Tarot Video Fabricator")
st.markdown("Generiere TikTok-Ready Videos aus deinen Audio- & Bild-Assets.")

# --- HELPER FUNCTIONS ---
def create_video(audio_file, illus_file, frame_file, zoom_strength=0.05, use_gpu=False):
    """
    Core Logic: Kombiniert Audio, Illustration und Rahmen zu einem Video.
    """
    
    # 1. Temporäre Dateien speichern (Streamlit handelt Uploads im RAM)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as t_audio:
        t_audio.write(audio_file.read())
        audio_path = t_audio.name

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as t_illus:
        t_illus.write(illus_file.read())
        illus_path = t_illus.name
        
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as t_frame:
        t_frame.write(frame_file.read())
        frame_path = t_frame.name

    audio_clip = None
    final_video = None

    try:
        # Optimize: Reduce memory usage by resizing images with Pillow BEFORE creating clips
        # This prevents MoviePy from loading massive 4K/8K images into RAM
        
        # Helper to strict resize
        def efficient_resize(img_path, target_width):
            with Image.open(img_path) as img:
                # Calculate new height to maintain aspect ratio
                ratio = target_width / float(img.size[0])
                new_size = (target_width, int(img.size[1] * ratio))
                return img.resize(new_size, Image.Resampling.LANCZOS)

        # 2. Audio laden & Dauer ermitteln
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration + 1.0 
        audio_clip = audio_clip.with_effects([AudioFadeOut(duration=1.0)])

        # 3. Background Processing
        # Resize manually with PIL to avoid memory spike in MoviePy
        with Image.open(illus_path) as img:
             # Calculate ratio to cover 1080x1920
             img_w, img_h = img.size
             scale = max(TIKTOK_SIZE[0]/img_w, TIKTOK_SIZE[1]/img_h) * 1.2
             new_w = int(img_w * scale)
             new_h = int(img_h * scale)
             bg_img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
             
             # Crop to 1080x1920 (center)
             left = (new_w - TIKTOK_SIZE[0]) // 2
             top = (new_h - TIKTOK_SIZE[1]) // 2
             bg_img = bg_img.crop((left, top, left + TIKTOK_SIZE[0], top + TIKTOK_SIZE[1]))
             
             # Save optimized bg to temp to let MoviePy read a smaller file
             # Limitation: MoviePy ImageClip reads from file best
             bg_temp_path = illus_path + "_bg_opt.png"
             bg_img.save(bg_temp_path)

        bg_clip = ImageClip(bg_temp_path).with_duration(duration)
        bg_clip = bg_clip.with_opacity(0.4) 

        # Schwarzer Canvas darunter
        canvas = ColorClip(size=TIKTOK_SIZE, color=(10,10,10), duration=duration)
        
        # 4. Haupt-Illustration (Der Fokus)
        # Pre-calculate main art size
        art_target_w = int(TIKTOK_SIZE[0] * 0.85)
        
        with Image.open(illus_path) as img:
            ratio = art_target_w / float(img.size[0])
            new_h = int(img.size[1] * ratio)
            art_img = img.resize((art_target_w, new_h), Image.Resampling.LANCZOS)
            art_temp_path = illus_path + "_art_opt.png"
            art_img.save(art_temp_path)

        art_clip = ImageClip(art_temp_path).with_duration(duration)
        art_clip = art_clip.with_position(("center", "center"))

        if zoom_strength > 0.0:
            try:
                 # We use a very slight zoom to avoid huge memory usage during resize
                 # Transforming a smaller image is better
                 art_clip = art_clip.with_effects([Resize(new_size=lambda t: 1 + (zoom_strength * t))])
            except Exception as e:
                 st.warning(f"Zoom effect disabled: {e}")

        # 5. Der Rahmen / Overlay 
        # Resize frame exactly to Target Size with PIL
        with Image.open(frame_path) as img:
            frame_img = img.resize(TIKTOK_SIZE, Image.Resampling.LANCZOS)
            frame_temp_path = frame_path + "_opt.png"
            frame_img.save(frame_temp_path)

        frame_clip = ImageClip(frame_temp_path).with_duration(duration)
        frame_clip = frame_clip.with_position(("center", "center"))

        # 6. Compositing 
        # Standard compositing can still be heavy. 
        # We ensure all clips are strictly typed and sized.
        
        # FAST MODE OPTIMIZATION
        # If no zoom is applied, we pre-render the entire frame with Pillow.
        # This completely bypasses MoviePy's frame-by-frame compositing.
        if zoom_strength == 0.0:
             # Load images again with PIL for clean compositing
             with Image.open(bg_temp_path) as bg_pil, \
                  Image.open(art_temp_path) as art_pil, \
                  Image.open(frame_temp_path) as frame_pil:
                
                # Create base canvas/artwork layer
                # Ensure Alpha channels
                bg_pil = bg_pil.convert("RGBA")
                art_pil = art_pil.convert("RGBA")
                frame_pil = frame_pil.convert("RGBA")
                
                # Composite Background (already sized)
                # Apply opacity manually? Pillow puts it on top. 
                # Better: Blend manually
                # Create a black canvas
                canvas_pil = Image.new("RGBA", TIKTOK_SIZE, (10,10,10, 255))
                
                # Blend BG with opacity 0.4
                # To do this in PIL:
                # 1. Paste BG
                # 2. Blend with constant alpha using putalpha? 
                # Easier: enhance brightness? No, opacity.
                bg_pil.putalpha(int(255 * 0.4)) 
                
                # Paste BG on Canvas
                # Center it? It's already cropped to TIKTOK_SIZE in step 3
                canvas_pil.alpha_composite(bg_pil, (0,0))
                
                # Paste Art (Centered)
                art_x = (TIKTOK_SIZE[0] - art_pil.width) // 2
                art_y = (TIKTOK_SIZE[1] - art_pil.height) // 2
                canvas_pil.alpha_composite(art_pil, (art_x, art_y))
                
                # Paste Frame (Centered/Full)
                canvas_pil.alpha_composite(frame_pil, (0,0))
                
                # Save static composite
                static_composite_path = tempfile.mktemp(suffix=".png")
                canvas_pil.save(static_composite_path)
                
                # Create simple clip
                final_video = ImageClip(static_composite_path).with_duration(duration)
                
        else:
            # DYNAMIC MODE (Zoom enabled)
            # Use MoviePy compositing (slower, but dynamic)
            final_video = CompositeVideoClip([
                canvas,
                bg_clip,      
                art_clip,     
                frame_clip    
            ], size=TIKTOK_SIZE)

        final_video = final_video.with_audio(audio_clip)

        # 7. Export with efficient settings
        output_path = tempfile.mktemp(suffix=".mp4")
        
        # GPU / CPU Rendering Logic
        if use_gpu:
             final_video.write_videofile(
                output_path, 
                fps=FPS, 
                codec="h264_nvenc", 
                audio_codec="aac",
                preset="p2", # Fast preset for NVENC (Speed priority)
                threads=4,
                ffmpeg_params=["-rc", "vbr"]
            )
        else:
            final_video.write_videofile(
                output_path, 
                fps=FPS, 
                codec="libx264", 
                audio_codec="aac",
                preset="faster", # faster encoding uses less memory than medium usually
                threads=2       # Reduce threads to save memory per thread
            )
        
        # Cleanup intermediate optimized files
        try:
            if os.path.exists(bg_temp_path): os.remove(bg_temp_path)
            if os.path.exists(art_temp_path): os.remove(art_temp_path)
            if os.path.exists(frame_temp_path): os.remove(frame_temp_path)
        except:
             pass

        return output_path

    except Exception as e:
        st.error(f"Fehler im Algorithmus: {e}")
        import traceback
        st.code(traceback.format_exc())
        return None
        
    finally:
        # Cleanup
        try:
            if audio_clip: audio_clip.close()
            # if final_video: final_video.close()
            pass
        except:
            pass
        
        # Files removal deferred or handled by OS cleanups (to avoid lock issues while streamlit holds file)

# --- UI LOGIC ---
col1, col2 = st.columns([1, 2])

with col1:
    st.header("1. Input Data")
    uploaded_audio = st.file_uploader("Audio Track (.mp3)", type=["mp3"])
    uploaded_illus = st.file_uploader("Illustration (Art)", type=["png", "jpg", "jpeg"])
    uploaded_frame = st.file_uploader("Rahmen/Overlay (.png Transparent)", type=["png"])
    
    st.write("---")
    st.info("💡 Tipp: Setze Zoom auf 0.0 für maximale Geschwindigkeit (vermeidet CPU-Resizing pro Frame).")
    zoom_level = st.slider("Zoom-Intensität (Vibe)", 0.0, 0.1, 0.04)
    use_gpu = st.checkbox("Use GPU Acceleration (Local Only - NVENC)", value=False)

with col2:
    st.header("2. Preview & Output")
    
    if uploaded_audio and uploaded_illus and uploaded_frame:
        if st.button("🚀 Render Video"):
            with st.spinner("Processing Pixel Data... blending realities..."):
                video_path = create_video(
                    uploaded_audio, 
                    uploaded_illus, 
                    uploaded_frame,
                    zoom_strength=zoom_level,
                    use_gpu=use_gpu
                )
                
                if video_path:
                    st.success("Video erfolgreich materialisiert!")
                    st.video(video_path)
                    
                    # Download Button
                    with open(video_path, "rb") as file:
                        btn = st.download_button(
                            label="📥 Download .mp4",
                            data=file,
                            file_name="tarot_tok_ready.mp4",
                            mime="video/mp4"
                        )
    else:
        st.info("Bitte lade alle Assets hoch, um den Prozess zu starten.")
