package com.cooingdv.rcufo.models;

import android.content.res.AssetFileDescriptor;
import android.graphics.Bitmap;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaCodecList;
import android.media.MediaCrypto;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.util.Log;
import android.view.Surface;
import androidx.work.Data;
import com.amazon.device.ads.DtbConstants;
import com.cooingdv.rcufo.base.BaseFragment;
import com.cooingdv.rcufo.interfaces.OnMusicComposeListener;
import com.cooingdv.rcufo.utils.AppUtils;
import com.cooingdv.rcufo.utils.Dbug;
import com.mbridge.msdk.playercommon.exoplayer2.util.MimeTypes;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.nio.ByteBuffer;
import tv.danmaku.ijk.media.player.IjkMediaMeta;
import tv.danmaku.ijk.media.player.misc.IMediaFormat;

/* JADX INFO: loaded from: classes2.dex */
public class VideoModel {
    private BaseFragment context;
    private boolean isRecording;
    private MediaExtractor mAudioExtractor;
    private ByteBuffer[] mDecodeInputBuffer;
    private ByteBuffer[] mDecodeOutputBuffer;
    private MediaCodec mDecoder;
    private ByteBuffer[] mEncodeInputBuffer;
    private ByteBuffer[] mEncodeOutputBuffer;
    private MediaCodec mEncoder;
    private MediaMuxer mMuxer;
    private int mTrackIndex;
    private MediaExtractor mVideoExtractor;
    private MediaCodec mediaCodec;
    private String musicComposeVideoPath;
    private String musicPath;
    private String name;
    private OnMusicComposeListener onMusicComposeListener;
    private int type;
    private String TAG = getClass().getSimpleName();
    private int width = 640;
    private int height = DtbConstants.DEFAULT_PLAYER_HEIGHT;
    private int fps = 20;
    private boolean isYUV420P = false;
    private long frameIndex = 0;
    private int timeoutUSec = 10000;
    private byte[] spsPpsInfo = null;
    private ByteArrayOutputStream baops = new ByteArrayOutputStream();
    private String currentVideoPath = "";
    private boolean isMusicComposeMode = false;
    private int MAX_INPUT_SIZE = Data.MAX_DATA_BYTES;
    private int VIDEO_READ_SAMPLE_SIZE = 524288;
    private int BIT_RATE = 65536;
    private int SAMPLE_RATE = 44100;
    private Long TIMEOUT_US = 1000L;
    private MediaMuxer mMediaMuxer = null;
    private int mAudioTrackIndex = -1;
    private int mVideoTrackIndex = -1;
    private long mMaxTimeStamp = 0;

    public VideoModel(BaseFragment baseFragment) {
        this.context = baseFragment;
    }

    public void setCurrentVideoPath(String str) {
        this.currentVideoPath = str;
    }

    public void setOnMusicComposeListener(OnMusicComposeListener onMusicComposeListener) {
        this.isMusicComposeMode = onMusicComposeListener != null;
        this.onMusicComposeListener = onMusicComposeListener;
    }

    public void setMusicPath(String str) {
        this.musicPath = str;
    }

    public void setType(int i) {
        this.type = i;
    }

    public void setName(String str) {
        this.name = str;
    }

    public void init(int i, int i2, int i3) {
        if (isRecording()) {
            stopRecorder();
        }
        this.width = i;
        this.height = i2;
        this.fps = i3;
        try {
            if (AppUtils.isSoftEncode(i)) {
                this.mediaCodec = MediaCodec.createByCodecName("OMX.google.h264.encoder");
                Dbug.m13286i(this.TAG, "use soft encoder");
            } else {
                this.mediaCodec = MediaCodec.createEncoderByType(MimeTypes.VIDEO_H264);
                Dbug.m13286i(this.TAG, "use hard encoder");
            }
            MediaFormat mediaFormatCreateVideoFormat = MediaFormat.createVideoFormat(MimeTypes.VIDEO_H264, i, i2);
            mediaFormatCreateVideoFormat.setInteger(IjkMediaMeta.IJKM_KEY_BITRATE, 2000000);
            mediaFormatCreateVideoFormat.setInteger("frame-rate", i3);
            mediaFormatCreateVideoFormat.setInteger("color-format", getSupportFormat(MimeTypes.VIDEO_H264));
            mediaFormatCreateVideoFormat.setInteger("i-frame-interval", 5);
            this.mediaCodec.configure(mediaFormatCreateVideoFormat, (Surface) null, (MediaCrypto) null, 1);
            this.mediaCodec.start();
            String str = "/REC_" + (System.currentTimeMillis() / 1000) + "_0.mp4";
            String videoPath = AppUtils.getVideoPath(this.context.getActivity());
            File file = new File(videoPath);
            if (!file.exists()) {
                file.mkdirs();
            }
            String str2 = videoPath + str;
            File file2 = new File(str2);
            if (!file2.exists()) {
                file2.createNewFile();
            }
            this.currentVideoPath = str2;
            this.mMuxer = new MediaMuxer(str2, 0);
            this.mTrackIndex = -1;
            this.frameIndex = 0L;
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private MediaCodecInfo selectCodec(String str) {
        int codecCount = MediaCodecList.getCodecCount();
        for (int i = 0; i < codecCount; i++) {
            MediaCodecInfo codecInfoAt = MediaCodecList.getCodecInfoAt(i);
            if (codecInfoAt.isEncoder()) {
                for (String str2 : codecInfoAt.getSupportedTypes()) {
                    if (str2.equalsIgnoreCase(str)) {
                        return codecInfoAt;
                    }
                }
            }
        }
        return null;
    }

    private int getSupportFormat(String str) {
        MediaCodecInfo mediaCodecInfoSelectCodec = selectCodec(str);
        int[] iArr = mediaCodecInfoSelectCodec != null ? mediaCodecInfoSelectCodec.getCapabilitiesForType(str).colorFormats : null;
        if (iArr == null) {
            return 2135033992;
        }
        for (int i : iArr) {
            if (i == 21) {
                Log.e("CODELIST", "" + i);
                return i;
            }
        }
        for (int i2 : iArr) {
            if (i2 == 19) {
                Log.e("CODELIST", "" + i2);
                this.isYUV420P = true;
                return i2;
            }
        }
        return 2135033992;
    }

    public void startRecorder() {
        this.isRecording = true;
    }

    public int[] bitmap2argb(Bitmap bitmap) {
        int width = bitmap.getWidth();
        int height = bitmap.getHeight();
        int[] iArr = new int[width * height];
        bitmap.getPixels(iArr, 0, width, 0, 0, width, height);
        return iArr;
    }

    public boolean isRecording() {
        return this.isRecording;
    }

    public void setYUV420P(boolean z) {
        this.isYUV420P = z;
    }

    public boolean isYUV420P() {
        return this.isYUV420P;
    }

    private long computePresentationTime(long j, int i) {
        return ((j * 1000000) / ((long) i)) + 132;
    }

    public byte[] offerEncoder(byte[] bArr) {
        try {
            ByteBuffer[] inputBuffers = this.mediaCodec.getInputBuffers();
            ByteBuffer[] outputBuffers = this.mediaCodec.getOutputBuffers();
            int iDequeueInputBuffer = this.mediaCodec.dequeueInputBuffer(-1L);
            if (iDequeueInputBuffer >= 0) {
                long jComputePresentationTime = computePresentationTime(this.frameIndex, this.fps);
                ByteBuffer byteBuffer = inputBuffers[iDequeueInputBuffer];
                byteBuffer.clear();
                byteBuffer.put(bArr, 0, bArr.length);
                this.mediaCodec.queueInputBuffer(iDequeueInputBuffer, 0, bArr.length, jComputePresentationTime, 0);
                this.frameIndex++;
            }
            MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();
            int iDequeueOutputBuffer = this.mediaCodec.dequeueOutputBuffer(bufferInfo, this.timeoutUSec);
            Log.e("outputBufferIndex=", iDequeueOutputBuffer + "");
            if (iDequeueOutputBuffer == -2) {
                this.mTrackIndex = this.mMuxer.addTrack(this.mediaCodec.getOutputFormat());
                this.mMuxer.start();
            }
            while (iDequeueOutputBuffer >= 0) {
                ByteBuffer byteBuffer2 = outputBuffers[iDequeueOutputBuffer];
                int i = bufferInfo.size;
                byte[] bArr2 = new byte[i];
                byteBuffer2.get(bArr2);
                if (this.spsPpsInfo == null) {
                    if (ByteBuffer.wrap(bArr2).getInt() != 1) {
                        return null;
                    }
                    byte[] bArr3 = new byte[i];
                    this.spsPpsInfo = bArr3;
                    System.arraycopy(bArr2, 0, bArr3, 0, i);
                } else {
                    this.baops.write(bArr2);
                }
                if (bufferInfo.size != 0) {
                    byteBuffer2.position(bufferInfo.offset);
                    byteBuffer2.limit(bufferInfo.offset + bufferInfo.size);
                    this.mMuxer.writeSampleData(this.mTrackIndex, byteBuffer2, bufferInfo);
                }
                this.mediaCodec.releaseOutputBuffer(iDequeueOutputBuffer, false);
                iDequeueOutputBuffer = this.mediaCodec.dequeueOutputBuffer(bufferInfo, this.timeoutUSec);
            }
            byte[] byteArray = this.baops.toByteArray();
            if (byteArray.length > 5 && byteArray[4] == 101) {
                this.baops.reset();
                this.baops.write(this.spsPpsInfo);
                this.baops.write(byteArray);
            }
        } catch (Throwable th) {
            th.printStackTrace();
        }
        byte[] byteArray2 = this.baops.toByteArray();
        this.baops.reset();
        return byteArray2;
    }

    private void YUV420SP2YUV420(byte[] bArr, byte[] bArr2, int i, int i2) {
        int i3;
        if (bArr == null) {
            return;
        }
        int i4 = i * i2;
        int i5 = 0;
        for (int i6 = 0; i6 < i4; i6++) {
            bArr2[i6] = bArr[i6];
        }
        int i7 = 0;
        int i8 = 0;
        while (true) {
            i3 = i4 / 2;
            if (i7 >= i3) {
                break;
            }
            bArr2[i8 + i4] = bArr[i7 + i4];
            i8++;
            i7 += 2;
        }
        for (int i9 = 1; i9 < i3; i9 += 2) {
            bArr2[((i4 * 5) / 4) + i5] = bArr[i9 + i4];
            i5++;
        }
    }

    public void encodeYUV420SP(byte[] bArr, byte[] bArr2, int[] iArr, int i, int i2) {
        int i3 = i * i2;
        int i4 = 0;
        int i5 = 0;
        for (int i6 = 0; i6 < i2; i6++) {
            int i7 = 0;
            while (i7 < i) {
                int i8 = iArr[i4];
                int i9 = (16711680 & i8) >> 16;
                int i10 = (65280 & i8) >> 8;
                int i11 = 255;
                int i12 = i8 & 255;
                int i13 = (((((i9 * 66) + (i10 * 129)) + (i12 * 25)) + 128) >> 8) + 16;
                int i14 = (((((i9 * (-38)) - (i10 * 74)) + (i12 * 112)) + 128) >> 8) + 128;
                int i15 = (((((i9 * 112) - (i10 * 94)) - (i12 * 18)) + 128) >> 8) + 128;
                int i16 = i5 + 1;
                if (i13 < 0) {
                    i13 = 0;
                } else if (i13 > 255) {
                    i13 = 255;
                }
                bArr[i5] = (byte) i13;
                if (i6 % 2 == 0 && i4 % 2 == 0) {
                    int i17 = i3 + 1;
                    if (i14 < 0) {
                        i14 = 0;
                    } else if (i14 > 255) {
                        i14 = 255;
                    }
                    bArr[i3] = (byte) i14;
                    i3 += 2;
                    if (i15 < 0) {
                        i11 = 0;
                    } else if (i15 <= 255) {
                        i11 = i15;
                    }
                    bArr[i17] = (byte) i11;
                }
                i4++;
                i7++;
                i5 = i16;
            }
        }
        if (this.isYUV420P) {
            YUV420SP2YUV420(bArr, bArr2, i, i2);
        }
    }

    public void close() {
        try {
            this.mediaCodec.stop();
            this.mediaCodec.release();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    public void stopRecorder() {
        this.isRecording = false;
        try {
            close();
            MediaMuxer mediaMuxer = this.mMuxer;
            if (mediaMuxer != null) {
                mediaMuxer.stop();
                this.mMuxer.release();
                this.mMuxer = null;
            }
            this.frameIndex = 0L;
            if (!this.isMusicComposeMode) {
                updateGallery();
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
        startCompose();
    }

    public void startCompose() {
        if (this.isMusicComposeMode) {
            this.mVideoExtractor = new MediaExtractor();
            this.mAudioExtractor = new MediaExtractor();
            new Thread(new Runnable() { // from class: com.cooingdv.rcufo.models.VideoModel.1
                @Override // java.lang.Runnable
                public void run() {
                    VideoModel.this.start();
                }
            }).start();
        }
    }

    public void start() {
        OnMusicComposeListener onMusicComposeListener = this.onMusicComposeListener;
        if (onMusicComposeListener != null) {
            onMusicComposeListener.onComposeStart();
        }
        boolean zInitDecodeAudio = initDecodeAudio();
        boolean zInitEncodeAudio = initEncodeAudio();
        boolean zInitMuxer = initMuxer();
        if (zInitMuxer) {
            if (handleTrack(this.mMediaMuxer, this.mVideoTrackIndex, this.mVideoExtractor)) {
                decodeInputBuffer();
            } else {
                Dbug.m13285e(this.TAG, "handlerTrack is fail!");
            }
        }
        Dbug.m13285e(this.TAG, "init message :initDecodeAudio = " + zInitDecodeAudio + "initEncodeAudio = " + zInitEncodeAudio + "initMuxer" + zInitMuxer);
        closeCompose();
        File file = new File(this.currentVideoPath);
        if (file.exists()) {
            file.delete();
        }
        this.currentVideoPath = this.musicComposeVideoPath;
        updateGallery();
        OnMusicComposeListener onMusicComposeListener2 = this.onMusicComposeListener;
        if (onMusicComposeListener2 != null) {
            onMusicComposeListener2.onComposeFinish();
        }
    }

    private void closeCompose() {
        try {
            MediaMuxer mediaMuxer = this.mMediaMuxer;
            if (mediaMuxer != null) {
                mediaMuxer.stop();
                this.mMediaMuxer.release();
                this.mMediaMuxer = null;
            }
            this.mAudioExtractor.release();
            this.mAudioExtractor = null;
            this.mVideoExtractor.release();
            this.mVideoExtractor = null;
            this.mDecoder.stop();
            this.mDecoder.release();
            this.mEncoder.stop();
            this.mEncoder.release();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private boolean initMuxer() {
        MediaCodec mediaCodec;
        try {
            MediaFormat mediaFormat = getMediaFormat(this.mVideoExtractor, MimeTypes.VIDEO_H264, 3, this.currentVideoPath);
            if (mediaFormat == null) {
                Dbug.m13285e(this.TAG, "mVideoFormat = null");
                return false;
            }
            this.musicComposeVideoPath = AppUtils.getVideoPath(this.context.getActivity()) + ("/REC_" + (System.currentTimeMillis() / 1000) + "_0.mp4");
            MediaMuxer mediaMuxer = new MediaMuxer(this.musicComposeVideoPath, 0);
            this.mMediaMuxer = mediaMuxer;
            this.mVideoTrackIndex = mediaMuxer.addTrack(mediaFormat);
            Dbug.m13285e(this.TAG, " video long is : " + mediaFormat.getLong("durationUs"));
            this.mMaxTimeStamp = mediaFormat.getLong("durationUs");
            if (this.mDecoder != null && (mediaCodec = this.mEncoder) != null) {
                this.mAudioTrackIndex = this.mMediaMuxer.addTrack(mediaCodec.getOutputFormat());
                this.mMediaMuxer.start();
                return true;
            }
            return false;
        } catch (IOException e) {
            e.printStackTrace();
            this.mMediaMuxer = null;
        }
    }

    private void decodeOutputBuffer() {
        MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();
        int iDequeueOutputBuffer = this.mDecoder.dequeueOutputBuffer(bufferInfo, -1L);
        if (iDequeueOutputBuffer >= 0) {
            int i = bufferInfo.size;
            byte[] bArr = new byte[i];
            this.mDecodeOutputBuffer[iDequeueOutputBuffer].position(bufferInfo.offset);
            this.mDecodeOutputBuffer[iDequeueOutputBuffer].limit(bufferInfo.offset + bufferInfo.size);
            this.mDecodeOutputBuffer[iDequeueOutputBuffer].get(bArr);
            this.mDecodeOutputBuffer[iDequeueOutputBuffer].clear();
            this.mDecoder.releaseOutputBuffer(iDequeueOutputBuffer, false);
            if (i > 0) {
                encodeData(bArr, bufferInfo.presentationTimeUs);
            }
        }
    }

    private synchronized void encodeData(byte[] bArr, long j) {
        int iDequeueInputBuffer = this.mEncoder.dequeueInputBuffer(-1L);
        if (iDequeueInputBuffer >= 0) {
            ByteBuffer byteBuffer = this.mEncodeInputBuffer[iDequeueInputBuffer];
            byteBuffer.clear();
            byteBuffer.put(bArr);
            this.mEncoder.queueInputBuffer(iDequeueInputBuffer, 0, bArr.length, j, 0);
        }
        MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();
        int iDequeueOutputBuffer = this.mEncoder.dequeueOutputBuffer(bufferInfo, 0L);
        while (iDequeueOutputBuffer >= 0) {
            int i = bufferInfo.size;
            ByteBuffer byteBuffer2 = this.mEncodeOutputBuffer[iDequeueOutputBuffer];
            byteBuffer2.position(bufferInfo.offset);
            byteBuffer2.limit(bufferInfo.offset + i);
            this.mMediaMuxer.writeSampleData(this.mAudioTrackIndex, byteBuffer2, bufferInfo);
            this.mEncoder.releaseOutputBuffer(iDequeueOutputBuffer, false);
            iDequeueOutputBuffer = this.mEncoder.dequeueOutputBuffer(bufferInfo, 0L);
        }
    }

    private void decodeInputBuffer() {
        while (true) {
            int iDequeueInputBuffer = this.mDecoder.dequeueInputBuffer(this.TIMEOUT_US.longValue());
            if (iDequeueInputBuffer >= 0) {
                this.mDecodeInputBuffer[iDequeueInputBuffer].clear();
                long sampleTime = this.mAudioExtractor.getSampleTime();
                int sampleData = this.mAudioExtractor.readSampleData(this.mDecodeInputBuffer[iDequeueInputBuffer], 0);
                if (sampleData <= 0) {
                    continue;
                } else {
                    if (sampleTime > this.mMaxTimeStamp) {
                        return;
                    }
                    this.mDecoder.queueInputBuffer(iDequeueInputBuffer, 0, sampleData, sampleTime, 0);
                    this.mAudioExtractor.advance();
                    decodeOutputBuffer();
                }
            }
        }
    }

    private boolean initEncodeAudio() {
        try {
            this.mEncoder = MediaCodec.createByCodecName("OMX.google.aac.encoder");
            MediaFormat mediaFormatCreateAudioFormat = MediaFormat.createAudioFormat(MimeTypes.AUDIO_AAC, this.SAMPLE_RATE, 2);
            mediaFormatCreateAudioFormat.setInteger("aac-profile", 2);
            mediaFormatCreateAudioFormat.setInteger(IjkMediaMeta.IJKM_KEY_BITRATE, this.BIT_RATE);
            mediaFormatCreateAudioFormat.setInteger("max-input-size", this.MAX_INPUT_SIZE);
            this.mEncoder.configure(mediaFormatCreateAudioFormat, (Surface) null, (MediaCrypto) null, 1);
            this.mEncoder.start();
            this.mEncodeInputBuffer = this.mEncoder.getInputBuffers();
            this.mEncodeOutputBuffer = this.mEncoder.getOutputBuffers();
            return true;
        } catch (Exception e) {
            e.printStackTrace();
            Log.e(this.TAG, "initEncodeAudio---" + e.getMessage());
            return false;
        }
    }

    private boolean initDecodeAudio() {
        try {
            MediaFormat mediaFormat = getMediaFormat(this.mAudioExtractor, "audio/", this.type, this.musicPath);
            String string = mediaFormat.getString(IMediaFormat.KEY_MIME);
            Log.e(this.TAG, "设置decoder的音频格式是：" + string);
            MediaCodec mediaCodecCreateDecoderByType = MediaCodec.createDecoderByType(string);
            this.mDecoder = mediaCodecCreateDecoderByType;
            mediaCodecCreateDecoderByType.configure(mediaFormat, (Surface) null, (MediaCrypto) null, 0);
            this.mDecoder.start();
            this.mDecodeInputBuffer = this.mDecoder.getInputBuffers();
            this.mDecodeOutputBuffer = this.mDecoder.getOutputBuffers();
            return true;
        } catch (Exception e) {
            e.printStackTrace();
            Log.e(this.TAG, "initDecodeAudio---" + e.getMessage());
            return false;
        }
    }

    private boolean handleTrack(MediaMuxer mediaMuxer, int i, MediaExtractor mediaExtractor) {
        if (mediaMuxer == null || i < 0 || mediaExtractor == null) {
            return false;
        }
        ByteBuffer byteBufferAllocate = ByteBuffer.allocate(this.VIDEO_READ_SAMPLE_SIZE);
        MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();
        while (true) {
            int sampleData = mediaExtractor.readSampleData(byteBufferAllocate, 0);
            if (sampleData <= 0) {
                return true;
            }
            bufferInfo.offset = 0;
            bufferInfo.size = sampleData;
            bufferInfo.flags = mediaExtractor.getSampleFlags();
            bufferInfo.presentationTimeUs = mediaExtractor.getSampleTime();
            if (this.mMaxTimeStamp < bufferInfo.presentationTimeUs) {
                return true;
            }
            mediaExtractor.advance();
            mediaMuxer.writeSampleData(i, byteBufferAllocate, bufferInfo);
        }
    }

    private MediaFormat getMediaFormat(MediaExtractor mediaExtractor, String str, int i, String str2) {
        try {
            if (i == 3) {
                mediaExtractor.setDataSource(str2);
            } else {
                AssetFileDescriptor assetFileDescriptorOpenFd = this.context.getActivity().getAssets().openFd("music/" + this.name);
                mediaExtractor.setDataSource(assetFileDescriptorOpenFd.getFileDescriptor(), assetFileDescriptorOpenFd.getStartOffset(), assetFileDescriptorOpenFd.getLength());
            }
            for (int i2 = 0; i2 < mediaExtractor.getTrackCount(); i2++) {
                MediaFormat trackFormat = mediaExtractor.getTrackFormat(i2);
                if (trackFormat.getString(IMediaFormat.KEY_MIME).startsWith(str)) {
                    mediaExtractor.selectTrack(i2);
                    return trackFormat;
                }
            }
        } catch (IOException e) {
            e.printStackTrace();
        }
        Dbug.m13285e(this.TAG, "return null");
        return null;
    }

    private void updateGallery() {
        if (this.currentVideoPath.isEmpty()) {
            return;
        }
        File file = new File(this.currentVideoPath);
        if (file.exists()) {
            AppUtils.mediaScanVideo(this.context.getActivity(), file);
        }
    }
}
