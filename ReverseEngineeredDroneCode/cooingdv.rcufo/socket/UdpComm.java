package com.cooingdv.rcufo.socket;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketException;
import java.net.UnknownHostException;
import java.util.Arrays;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.locks.ReentrantLock;

/* JADX INFO: loaded from: classes2.dex */
public class UdpComm {
    private static UdpComm instance;
    private InetAddress address;
    private UdpCommCallback callback;
    private int port;
    private RecvDataThread recvDataThread;
    private SendDataThread sendDataThread;
    private DatagramSocket socket;

    public interface UdpCommCallback {
        void onReceiveData(byte[] bArr);
    }

    private UdpComm(String str, int i) {
        createClient(str, i);
    }

    public static UdpComm getInstance(String str, int i) {
        UdpComm udpComm = instance;
        if (udpComm != null) {
            return udpComm;
        }
        UdpComm udpComm2 = new UdpComm(str, i);
        instance = udpComm2;
        return udpComm2;
    }

    /* JADX INFO: Access modifiers changed from: private */
    public int sendData(byte[] bArr) {
        if (bArr == null || bArr.length <= 0) {
            return 0;
        }
        try {
            this.socket.send(new DatagramPacket(bArr, bArr.length, this.address, this.port));
            return 1;
        } catch (IOException e) {
            e.printStackTrace();
            return -1;
        } catch (Exception e2) {
            e2.printStackTrace();
            return -1;
        }
    }

    public void createClient(String str, int i) {
        this.port = i;
        try {
            this.socket = new DatagramSocket();
        } catch (SocketException e) {
            e.printStackTrace();
        }
        if (str == null || str.length() == 0) {
            return;
        }
        try {
            this.address = InetAddress.getByName(str);
        } catch (UnknownHostException e2) {
            e2.printStackTrace();
        }
    }

    public boolean isSendThreadRunning() {
        SendDataThread sendDataThread = this.sendDataThread;
        return sendDataThread != null && sendDataThread.running;
    }

    public void initSendRecvThread() {
        initRecvThread();
        initSendThread();
    }

    private void initSendThread() {
        SendDataThread sendDataThread = this.sendDataThread;
        if (sendDataThread == null) {
            SendDataThread sendDataThread2 = new SendDataThread();
            this.sendDataThread = sendDataThread2;
            sendDataThread2.running = true;
            this.sendDataThread.start();
            return;
        }
        if (!sendDataThread.isAlive()) {
            SendDataThread sendDataThread3 = new SendDataThread();
            this.sendDataThread = sendDataThread3;
            sendDataThread3.running = true;
            this.sendDataThread.start();
            return;
        }
        if (this.sendDataThread.running) {
            return;
        }
        this.sendDataThread.running = true;
    }

    private void initRecvThread() {
        RecvDataThread recvDataThread = this.recvDataThread;
        if (recvDataThread == null) {
            RecvDataThread recvDataThread2 = new RecvDataThread();
            this.recvDataThread = recvDataThread2;
            recvDataThread2.running = true;
            this.recvDataThread.start();
            return;
        }
        if (!recvDataThread.isAlive()) {
            RecvDataThread recvDataThread3 = new RecvDataThread();
            this.recvDataThread = recvDataThread3;
            recvDataThread3.running = true;
            this.recvDataThread.start();
            return;
        }
        if (this.recvDataThread.running) {
            return;
        }
        this.recvDataThread.running = true;
    }

    public void send(byte[] bArr) {
        SendDataThread sendDataThread = this.sendDataThread;
        if (sendDataThread == null || !sendDataThread.running || bArr == null || bArr.length <= 0) {
            return;
        }
        this.sendDataThread.putData(bArr);
    }

    public void stopSendDataThread() {
        SendDataThread sendDataThread = this.sendDataThread;
        if (sendDataThread != null) {
            if (sendDataThread.running) {
                this.sendDataThread.reset();
            }
            this.sendDataThread.interrupt();
            this.sendDataThread = null;
        }
    }

    public void stopRecvDataThread() {
        RecvDataThread recvDataThread = this.recvDataThread;
        if (recvDataThread != null) {
            if (recvDataThread.running) {
                this.recvDataThread.reset();
            }
            this.recvDataThread.interrupt();
            this.recvDataThread = null;
        }
    }

    public void closeClient() {
        instance = null;
        DatagramSocket datagramSocket = this.socket;
        if (datagramSocket != null) {
            datagramSocket.close();
            this.socket = null;
        }
        if (this.address != null) {
            this.address = null;
        }
    }

    private class SendDataThread extends Thread {
        private final ReentrantLock lock;
        private final LinkedBlockingDeque<byte[]> queue;
        private boolean running;

        private SendDataThread() {
            this.queue = new LinkedBlockingDeque<>();
            this.running = false;
            this.lock = new ReentrantLock();
        }

        /* JADX INFO: Access modifiers changed from: private */
        public void putData(byte[] bArr) {
            this.lock.lock();
            if (this.queue.remainingCapacity() <= 0) {
                this.queue.poll();
            } else {
                try {
                    this.queue.put(bArr);
                } catch (InterruptedException e) {
                    e.printStackTrace();
                }
            }
            this.lock.unlock();
        }

        @Override // java.lang.Thread
        public synchronized void start() {
            super.start();
        }

        public void reset() {
            this.running = false;
            this.queue.clear();
        }

        @Override // java.lang.Thread, java.lang.Runnable
        public void run() {
            while (this.running) {
                this.lock.lock();
                byte[] bArrPoll = this.queue.poll();
                if (bArrPoll == null) {
                    this.lock.unlock();
                } else {
                    this.lock.unlock();
                    if (UdpComm.this.sendData(bArrPoll) < 0) {
                        reset();
                    }
                }
            }
        }
    }

    private class RecvDataThread extends Thread {
        private boolean running;

        private RecvDataThread() {
            this.running = false;
        }

        public void reset() {
            this.running = false;
        }

        @Override // java.lang.Thread, java.lang.Runnable
        public void run() {
            while (this.running) {
                DatagramPacket datagramPacket = new DatagramPacket(new byte[20], 20);
                try {
                    UdpComm.this.socket.receive(datagramPacket);
                    byte[] bArrCopyOf = Arrays.copyOf(datagramPacket.getData(), datagramPacket.getLength());
                    if (UdpComm.this.callback != null) {
                        UdpComm.this.callback.onReceiveData(bArrCopyOf);
                    }
                } catch (Exception e) {
                    e.printStackTrace();
                }
            }
            reset();
        }
    }

    public void setCallback(UdpCommCallback udpCommCallback) {
        this.callback = udpCommCallback;
    }
}
