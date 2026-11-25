// The media types our video tools read, each with the one ffmpeg demuxer it is read with. Naming the demuxer stops a
// file from posing as a playlist (HLS, concat) that would make ffmpeg open other local files.
import { extname } from 'node:path';

export const DEMUXER = { '.mp4': 'mov', '.mov': 'mov', '.m4v': 'mov', '.m4a': 'mov', '.webm': 'matroska', '.mkv': 'matroska',
  '.mp3': 'mp3', '.wav': 'wav', '.aif': 'aiff', '.aiff': 'aiff', '.aac': 'aac', '.ogg': 'ogg', '.opus': 'ogg', '.ogv': 'ogg',
  '.png': 'image2', '.jpg': 'image2', '.jpeg': 'image2' };

// ffmpeg's input options for this file, or a refusal for a type not in the list.
export function demuxer(file) {
  const format = DEMUXER[extname(file).toLowerCase()];
  if (!format) throw new Error(`refused: ${file}: only ${Object.keys(DEMUXER).join(' ')} files`);
  return format === 'image2' ? ['-f', 'image2', '-pattern_type', 'none'] : ['-f', format];
}
