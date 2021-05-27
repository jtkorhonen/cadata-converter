#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import struct
import stat
from typing import Union, List, Optional, Any, Callable, Tuple, NamedTuple, ByteString, Sequence
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image


# Defaults for reading data files
HEADER_SIZE = 40

# Defaults for FFMPEG
CRF_VALUE = '21'
PROFILE = 'high'   # h.264 profile
PRESET = 'fast'   # encoding speed:compression ratio
FFMPEG_PATH = '/usr/local/bin/ffmpeg'   # path to ffmpeg bin
FFMPEG_VCODEC = "h264"   # or libx264


class DataFileTuple(NamedTuple):
    attr_file: Path
    data_file: Path
    out_dir: Optional[Path]

class FileInfoTuple(NamedTuple):
    width: int
    height: int
    ts_first: int
    ts_second: int
    ts_last: int
    dt: int
    dt_total: int
    frames: int
    fps: float
    duration: float
    pos_first: int
    pos_last: int



def read_width_and_height(attr_file: Path, 
                          width_pos: int = 19, 
                          height_pos: int = 37
                          ) -> Tuple[Any, Any] :
    """
    Reads width and height of the data file from 'attr' file.

    Parameters
    ----------
    attr_file
        File from where to read the width and height.
    width_pos (defautl: 19)
        The position (as bytes) of the width information, from the beginning of the file.
    height_pos (default: 37)
        The position (as bytes) of the height information, from the beginning of the file.
    """
    try:
        file_handle = os.open(attr_file, os.O_RDONLY)
        
        os.lseek(file_handle, width_pos, os.SEEK_SET) 
        height = struct.unpack('H', os.read(file_handle, 2))[0]
        #height_data = os.read(file_handle, 2)
        #height = int(height_data[1]) << 8 | int(height_data[0])
        
        os.lseek(file_handle, height_pos, os.SEEK_SET)
        width = struct.unpack('H', os.read(file_handle, 2))[0]
        #width_data = os.read(file_handle, 2)
        #width = int(width_data[1]) << 8 | int(width_data[0])
    except OSError as e:
        raise OSError from e
    except IOError as e:
        raise IOError from e
    except ValueError as e:
        raise ValueError from e
    finally:
        os.close(file_handle)

    return width, height


def read_timestamp(file_handle, reset_location: bool = False) -> Tuple[int]:
    """Reads a 12-byte timestamp into a datetime from the current location.

    Parameters
    ----------
    file_handle
        The file handle to use. It needs to have been opened using the `os.open` -method.
    reset_location (default: False)
        If True, the `file_handle` position is reset to the original location. If False, it will have been 
        moved forward by 12 bytes.
    """
    current_location = os.lseek(file_handle, 0, os.SEEK_CUR)

    ts_data_arr: List[int] = []
    for i in range(3):
        ts_data = struct.unpack('<I', os.read(file_handle, 4))[0]
        ts_data_arr.append(ts_data)

    if reset_location:
        os.lseek(file_handle, current_location, os.SEEK_SET)

    return tuple(ts_data_arr)


def read_frame(file_handle, 
               width: int,
               height: int,
               reset_location: bool = False) -> List[int]:
    """
    Reads a single frame of size `width`x`height` and returns the data as a one dimensional tuple.
    
    Parameters
    ----------
    file_handle
        Open file handle to the data, which needs to have been opened with `os.open`.
    width
        Width of the frame in pixels
    height
        Height of the frame in pixels
    reset_location (default: False)
        If True, the `file_handle` is redirected back to origianl position, if False, then the 
        position is not reset after reading.

    Returns
    -------
    List[int]
        The data read in as a one dimensional list.
    """
    current_location = os.lseek(file_handle, 0, os.SEEK_CUR)

    #data: List[int] = [int(data) for data in os.read(file_handle, width*height)]
    data: List[int] = [int(x) for x in os.read(file_handle, width*height)]

    if reset_location:
        os.lseek(file_handle, current_location, os.SEEK_SET)

    return data



def read_file_info(file_handle, 
                   width: int,
                   height: int,
                   reset_location: bool = False
                   ) -> FileInfoTuple:
    """
    Reads file information and returns it as a custom named tuple.

    Parameters
    ----------
    file_handle
        The `file_handle` to use. It needs to have been opened with `os.open` method.
    width
        The width of each image frame.
    height
        The height of each image frame.
    reset_location (default: False)
        If True, the file handle position is reset, otherwise it is undefined.

    Returns
    -------
    FileInfoTuple
        The data stored in a custom named tuple.
    """
    start_pos = os.lseek(file_handle, 0, os.SEEK_CUR)

    # Read the timestamp of the first image in sequence
    pos_first = os.lseek(file_handle, HEADER_SIZE, os.SEEK_SET)   # Move to the location of the first timestamp
    ts_first: int = read_timestamp(file_handle)  

    # Read the timestamp of the second image
    os.lseek(file_handle, width*height, os.SEEK_CUR)   # Move forward by the number of pixels
    ts_second: int = read_timestamp(file_handle)  

    # Read the timestapm of the last frame
    pos_last = os.lseek(file_handle, -(width*height+12), os.SEEK_END)
    ts_last: int = read_timestamp(file_handle)

    # Time between frames
    dt: int = ts_second[0] - ts_first[0]

    # Total time
    dt_total: int = ts_last[0] - ts_first[0]

    # Frames
    frames = int((pos_last - pos_first) / (width*height+12)) + 1

    # FPS
    fps: float = (frames-1)*1e6/dt_total

    # Video duration
    #duration: float = frames/fps
    duration: float = (ts_last[0]-ts_first[0]+dt)*1e-6

    if reset_location:
        os.lseek(file_handle, start_pos, os.SEEK_SET)

    return FileInfoTuple(
        width,
        height,
        ts_first,
        ts_second,
        ts_last,
        dt,
        dt_total,
        frames,
        fps,
        duration,
        pos_first,
        pos_last
    )


def read_data(data_file: Path, 
              attr_file: Path,
              out_dir: Path,
              *, 
              first_frame: int = 0, 
              last_frame: int = -1, 
              quality: int = 100, 
              framerate: Optional[int] = None,
              skipframes: int = 0,
              force_overwrite: bool = False
              ) -> None:
    """
    Extracts portion of contact angle meter and compresses it to a video
    using h.264 codec. All parameters are optional. Assumes constant
    framerate.

    Parameters
    ----------
    data_file: Path
        Path to the raw contact angle meter data.
    attr_file: Path
        Path to the attributes of the data_file.
    out_dir: Path
        Path where to store the image files.
    firstframe: int (default: 0)
        The first frame of the video to be extracted.
    lastframe: int (default: -1)
        The last frame of the video to be extracted. Value -1 is the last frame.
    quality: int (default: 100)
        The quality of the output video from 0 to 100
    framerate: Optional[int] (default: None)
        The framerate of output video. None means use same framerate as the source.
    skipframes: int (default: 0)
        The number of frames skipped between every saved frame. 0 means that every frame is processed.

    Examples
    --------   
    If you want to show 140 fps video in realtime, use framerate 28 and skipframes 4. Every fifth frame 
    is processed and will be played at 28 fps, which equals showing every frame at 140 fps (5*28=140).
    """
    width, height = read_width_and_height(attr_file)

    try:
        file_handle = os.open(data_file, os.O_RDONLY)
        file_info = read_file_info(file_handle, width, height)
        
        print(f"Timestamp (first)   : {file_info.ts_first[0]} us")
        print(f"Timestamp (second)  : {file_info.ts_second[0]} us")
        print(f"Timestamp (last)    : {file_info.ts_last[0]} us")
        print(f"Time between frames : {file_info.dt} us.")
        print(f"Total time          : {file_info.dt_total} us.")
        print(f"Frames              : {file_info.frames}")
        print(f"Frames per second   : {file_info.fps:.2f}")
        print(f"Duration            : {file_info.duration:.2f} s")
        
        if framerate is None:
            framerate = file_info.fps

        os.lseek(file_handle, file_info.pos_first, os.SEEK_SET)   # Go to first frame
        for i in range(file_info.frames):
            image_filename = out_dir / f"{i:04d}.png"
            if os.path.exists(image_filename):
                print(f"File exists, skipping: {image_filename}")
                os.lseek(file_handle, width*height+12, os.SEEK_CUR)
                continue

            ts = read_timestamp(file_handle)
            frame = read_frame(file_handle, width, height)

            image = Image.new('L', (height, width), None)   # Create a non-initialized image
            image.putdata(frame)

            
            print(f"Saving to {image_filename}...")
            image.save(image_filename, compress_level=9)


    except IOError as e:
        print(f"IOError encountered: {e}")
    except OSError as e:
        print(f"OSError encountered: {e}")
    except ValueError as e:
        print(f"ValueError encountered: {e}")
    finally:
        os.close(file_handle)








def run_test() -> None:
    data_path: Path = Path.cwd() / "data"

    data_files: List[DataFileTuple] = []

    # Find the attribute files
    attr_files: List = list(data_path.glob("**/camera?-attr"))
    assert len(attr_files) > 0, "Could not locate any attr files."

    # Find data files to go along the attribute files
    for attr_file in attr_files:
        #print(f"Attribute file: {attr_file}.")
        file_location = attr_file.parent
        attr_file_name = attr_file.name
        data_name = attr_file.parts[-4]
        
        data_file_name = attr_file_name.replace("attr", "data")
        data_file = Path(file_location, data_file_name)

        out_dir_name = data_name + "-" + attr_file_name.replace("attr", "data")
        output_path = Path.cwd() / "output"
        out_dir = Path(output_path, out_dir_name)

        if not os.path.isdir(out_dir):
            print(f"{out_dir} not found. Trying to create.")
            os.mkdir(out_dir)

        if not data_file.exists():
            #print(f"Could not find data file: {data_file}")
            raise FileNotFoundError(f"Could not find data file: {data_file}")
        elif not os.path.isdir(out_dir):
            raise IOError(f"Output directory does not exist: {out_dir}")
        else:
            data_files.append(DataFileTuple(attr_file = attr_file, data_file = data_file, out_dir = out_dir))

    assert len(data_files) > 0, "Could not locate any files."

    for file in data_files:
        print(f"Attribute file : {file.attr_file}")
        print(f"     Data file : {file.data_file}")
        print(f"       Out dir : {file.out_dir}")

        width, height = read_width_and_height(attr_file)
        print(f"         Width : {width}")
        print(f"        Height : {height}")

        framerate = 10
        read_data(file.data_file, file.attr_file, file.out_dir, framerate=framerate)

        convert_filename = file.out_dir / f"convert_cmd.sh"
        video_filename = file.out_dir / f"video.mp4"
        #ffmpeg_cmd = f"{FFMPEG_PATH} -r {framerate} -f image2 -s {width}x{height} -i {file.out_dir.absolute()}/%04d.png -vcodec {FFMPEG_VCODEC} -crf {CRF_VALUE} -pix_fmt yuv420p {video_filename.absolute()}"
        ffmpeg_cmd = [
            f"{FFMPEG_PATH}",
            f"-r {framerate}",
            "-f image2",
            f"-s {width}x{height}",
            f"-i {file.out_dir.absolute()}/%04d.png",
            f"-vcodec {FFMPEG_VCODEC}",
            f"-crf {CRF_VALUE}",
            f"-pix_fmt yuv420p",
            f"{video_filename.absolute()}"
            ]
        ffmpeg_cmd_str = " ".join(ffmpeg_cmd)
        if not os.path.exists(convert_filename):
            with open(convert_filename, 'w') as convert_file:
                convert_file.write("#!/bin/sh\n")
                convert_file.write(ffmpeg_cmd_str)
            os.chmod(convert_filename, stat.S_IEXEC | stat.S_IREAD | stat.S_IWRITE)

        if not os.path.exists(video_filename):
            print(f"Starting FFMPEG encoder: '{ffmpeg_cmd_str}'")
            try:
                #result = subprocess.run(ffmpeg_cmd, shell=True, check=False, capture_output=True, text=True)
                result = subprocess.run(ffmpeg_cmd_str, shell=True, check=False, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                print(f"Subprocess returned an error: '{e}'")
            else:
                print(f"Output: {result.stdout}")
                print(f"Errors: {result.stderr}")
            


if __name__ == "__main__":
    run_test()
