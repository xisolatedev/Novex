package com.cooingdv.rcufo.fragment;

import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.media.ThumbnailUtils;
import android.os.Bundle;
import android.os.Handler;
import android.os.Message;
import android.text.TextUtils;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.GridView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListAdapter;
import android.widget.RelativeLayout;
import android.widget.TextView;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.activity.PhotoViewActivity;
import com.cooingdv.rcufo.activity.VideoViewActivity;
import com.cooingdv.rcufo.base.BaseFragment;
import com.cooingdv.rcufo.beans.FileInfo;
import com.cooingdv.rcufo.dialog.NotifyDialog;
import com.cooingdv.rcufo.dialog.WaitingDialog;
import com.cooingdv.rcufo.libs.pullrefreshview.layout.BaseFooterView;
import com.cooingdv.rcufo.tools.BitmapCache;
import com.cooingdv.rcufo.tools.BufChangeHex;
import com.cooingdv.rcufo.tools.IConstants;
import com.cooingdv.rcufo.tools.ScanFilesHelper;
import com.cooingdv.rcufo.tools.TimeFormater;
import com.cooingdv.rcufo.utils.AppUtils;
import com.cooingdv.rcufo.utils.Dbug;
import com.vungle.ads.internal.model.AdPayload;
import com.vungle.ads.internal.protos.Sdk;
import java.io.File;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/* JADX INFO: loaded from: classes2.dex */
public class BrowseFileFragment extends BaseFragment implements View.OnClickListener, BaseFooterView.OnLoadListener, AdapterView.OnItemClickListener {
    private static final int DELETE_STYLE = 0;
    private String appFilePath;
    private ImageView btnAllSelect;
    private ImageView btnBack;
    private ImageView btnDownLoadFile;
    private ImageView btnEdit;
    private String dFileThumbPath;
    private NotifyDialog deleteNotifyDialog;
    private GridView gridView;
    private LinearLayout layoutEditMode;
    private BrowseFileAdapter mAdapter;
    private BitmapCache mBitmapCache;
    private ScanFilesHelper scanFilesHelper;
    private Map<String, String> thumbPathMap;
    private String title;
    private TextView tvCenter;
    private TextView tvTitle;
    private WaitingDialog waitingDeleteDialog;
    private WaitingDialog waitingDialog;
    private int failureTimes = 3;
    private int fileType = 1;
    private boolean isEditMode = false;
    private boolean isLoading = false;
    private boolean isDeleting = false;
    private boolean isTaskOpen = false;
    private boolean isRearViewBrowsing = false;
    private boolean isAllSelect = false;
    private ExecutorService service = null;
    private Future<String> future = null;
    private List<String> lastNameList = null;
    private Map<String, String> durationMap = null;
    private List<FileInfo> allDataList = null;
    private List<FileInfo> fileInfoList = null;
    private List<FileInfo> selectItemList = null;
    private Handler mHandler = new Handler(new Handler.Callback() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.1
        @Override // android.os.Handler.Callback
        public boolean handleMessage(Message message) {
            if (BrowseFileFragment.this.getActivity() != null && message != null && message.what == 258) {
                if (BrowseFileFragment.this.mHandler != null) {
                    BrowseFileFragment.this.mHandler.post(BrowseFileFragment.this.dismissWaitingDialog);
                }
                Dbug.m13285e(BrowseFileFragment.this.TAG, " >>>> -FtpHandlerThread.MSG_UPDATE_UI- ");
                BrowseFileFragment.this.allDataList = (List) message.obj;
                if (BrowseFileFragment.this.allDataList != null) {
                    if (BrowseFileFragment.this.fileInfoList != null) {
                        BrowseFileFragment.this.fileInfoList.clear();
                    }
                    if (BrowseFileFragment.this.allDataList.size() == 0) {
                        if (BrowseFileFragment.this.mAdapter != null) {
                            BrowseFileFragment.this.mAdapter.clear();
                            BrowseFileFragment.this.gridView.setAdapter((ListAdapter) BrowseFileFragment.this.mAdapter);
                        }
                        return false;
                    }
                    BrowseFileFragment browseFileFragment = BrowseFileFragment.this;
                    browseFileFragment.fileInfoList = browseFileFragment.selectTypeList(browseFileFragment.allDataList, BrowseFileFragment.this.fileType);
                    if (BrowseFileFragment.this.fileInfoList != null && BrowseFileFragment.this.fileInfoList.size() >= 0) {
                        List listSubList = BrowseFileFragment.this.fileInfoList.subList(0, BrowseFileFragment.this.fileInfoList.size());
                        if (BrowseFileFragment.this.mAdapter != null) {
                            BrowseFileFragment.this.mAdapter.clear();
                            BrowseFileFragment.this.mAdapter.addAll(listSubList);
                            BrowseFileFragment.this.gridView.setAdapter((ListAdapter) BrowseFileFragment.this.mAdapter);
                        } else {
                            BrowseFileFragment browseFileFragment2 = BrowseFileFragment.this;
                            BrowseFileFragment browseFileFragment3 = BrowseFileFragment.this;
                            browseFileFragment2.mAdapter = new BrowseFileAdapter(browseFileFragment3.getActivity().getApplicationContext());
                            BrowseFileFragment.this.mAdapter.addAll(listSubList);
                            BrowseFileFragment.this.gridView.setAdapter((ListAdapter) BrowseFileFragment.this.mAdapter);
                        }
                    }
                } else {
                    Dbug.m13285e(BrowseFileFragment.this.TAG, " -onMainAction- allDataList is null! ");
                    return false;
                }
            }
            return false;
        }
    });
    private Runnable loadMoreData = new Runnable() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.2
        @Override // java.lang.Runnable
        public void run() {
            if (BrowseFileFragment.this.fileInfoList == null || BrowseFileFragment.this.mAdapter == null) {
                return;
            }
            int size = BrowseFileFragment.this.fileInfoList.size();
            int count = BrowseFileFragment.this.mAdapter.getCount();
            if (size - count > 0) {
                BrowseFileFragment.this.mAdapter.addAll(BrowseFileFragment.this.fileInfoList.subList(count, BrowseFileFragment.this.fileInfoList.size()));
                BrowseFileFragment.this.mAdapter.notifyDataSetChanged();
            } else if (BrowseFileFragment.this.fileInfoList.size() == 0) {
                BrowseFileFragment.this.showShortToast(C3033R.string.no_file_tip);
            }
        }
    };
    private Runnable dismissWaitingDialog = new Runnable() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.3
        @Override // java.lang.Runnable
        public void run() {
            if (BrowseFileFragment.this.waitingDialog != null && BrowseFileFragment.this.waitingDialog.isShowing()) {
                BrowseFileFragment.this.waitingDialog.dismiss();
                Dbug.m13285e("ZZC", "waitingDialog dismiss!");
                BrowseFileFragment.this.waitingDialog = null;
            }
            if (BrowseFileFragment.this.mAdapter != null) {
                BrowseFileFragment.this.mAdapter.notifyDataSetChanged();
            }
            BrowseFileFragment.this.mHandler.removeCallbacks(BrowseFileFragment.this.dismissWaitingDialog);
        }
    };

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.fragment_browse_file, viewGroup, false);
        this.btnBack = (ImageView) viewInflate.findViewById(C3033R.id.browse_file_back_btn);
        this.btnEdit = (ImageView) viewInflate.findViewById(C3033R.id.browse_file_edit_btn);
        ImageView imageView = (ImageView) viewInflate.findViewById(C3033R.id.browse_file_delete_file_btn);
        this.btnDownLoadFile = (ImageView) viewInflate.findViewById(C3033R.id.browse_file_download_btn);
        this.tvTitle = (TextView) viewInflate.findViewById(C3033R.id.browse_file_title);
        this.layoutEditMode = (LinearLayout) viewInflate.findViewById(C3033R.id.browse_file_edit_mode);
        this.tvCenter = (TextView) viewInflate.findViewById(C3033R.id.browse_file_center_tv);
        this.gridView = (GridView) viewInflate.findViewById(C3033R.id.browse_file_grid_view);
        this.btnAllSelect = (ImageView) viewInflate.findViewById(C3033R.id.browse_file_all_select_btn);
        this.btnBack.setOnClickListener(this);
        this.btnEdit.setOnClickListener(this);
        imageView.setOnClickListener(this);
        this.btnDownLoadFile.setOnClickListener(this);
        this.gridView.setOnItemClickListener(this);
        this.btnAllSelect.setOnClickListener(this);
        return viewInflate;
    }

    @Override // androidx.fragment.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        super.onActivityCreated(bundle);
        if (getActivity() != null) {
            if (this.scanFilesHelper == null) {
                this.scanFilesHelper = new ScanFilesHelper(getActivity().getApplicationContext());
            }
            Bundle bundle2 = getBundle();
            if (bundle2 != null) {
                String string = bundle2.getString(IConstants.KEY_FILE_NAME);
                this.title = string;
                if (TextUtils.isEmpty(string)) {
                    return;
                }
                this.tvTitle.setText(this.title);
            }
        }
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public void onResume() {
        super.onResume();
        initParams();
        updateData(this.title);
        if (this.mApplication.getIsBrowsing()) {
            this.mApplication.setIsBrowsing(false);
        }
    }

    @Override // androidx.fragment.app.Fragment
    public void onStop() {
        super.onStop();
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public void onDetach() {
        super.onDetach();
        release();
    }

    @Override // android.view.View.OnClickListener
    public void onClick(View view) {
        if (getActivity() == null || view == null) {
            return;
        }
        switch (view.getId()) {
            case C3033R.id.browse_file_all_select_btn /* 2131296442 */:
                if (this.isEditMode) {
                    boolean z = !this.isAllSelect;
                    this.isAllSelect = z;
                    if (z) {
                        this.btnAllSelect.setImageResource(C3033R.drawable.drawable_all_select_yellow);
                        List<FileInfo> list = this.selectItemList;
                        if (list != null) {
                            list.clear();
                        } else {
                            this.selectItemList = new ArrayList();
                        }
                        List<FileInfo> list2 = this.fileInfoList;
                        if (list2 != null) {
                            for (FileInfo fileInfo : list2) {
                                if (fileInfo != null) {
                                    fileInfo.setSelected(true);
                                    this.selectItemList.add(fileInfo);
                                }
                            }
                            BrowseFileAdapter browseFileAdapter = this.mAdapter;
                            if (browseFileAdapter != null) {
                                browseFileAdapter.notifyDataSetChanged();
                            }
                            updateCenterTV(this.selectItemList.size(), this.fileInfoList.size());
                        }
                    } else {
                        this.btnAllSelect.setImageResource(C3033R.drawable.drawable_all_select);
                        List<FileInfo> list3 = this.selectItemList;
                        if (list3 != null) {
                            list3.clear();
                        } else {
                            this.selectItemList = new ArrayList();
                        }
                        List<FileInfo> list4 = this.fileInfoList;
                        if (list4 != null) {
                            for (FileInfo fileInfo2 : list4) {
                                if (fileInfo2 != null) {
                                    fileInfo2.setSelected(false);
                                }
                            }
                            updateCenterTV(this.selectItemList.size(), this.fileInfoList.size());
                        }
                        BrowseFileAdapter browseFileAdapter2 = this.mAdapter;
                        if (browseFileAdapter2 != null) {
                            browseFileAdapter2.notifyDataSetChanged();
                        }
                    }
                }
                break;
            case C3033R.id.browse_file_back_btn /* 2131296443 */:
                if (this.isEditMode) {
                    this.isEditMode = false;
                    this.isAllSelect = false;
                    this.isLoading = false;
                    this.isDeleting = false;
                    releaseDialog();
                    List<FileInfo> list5 = this.selectItemList;
                    if (list5 != null) {
                        list5.clear();
                    }
                    this.tvCenter.setText("");
                    this.tvCenter.setVisibility(8);
                    this.layoutEditMode.setVisibility(8);
                    this.tvTitle.setVisibility(0);
                    this.btnEdit.setVisibility(0);
                    this.btnAllSelect.setImageResource(C3033R.drawable.drawable_all_select);
                    BrowseFileAdapter browseFileAdapter3 = this.mAdapter;
                    if (browseFileAdapter3 != null) {
                        browseFileAdapter3.notifyDataSetChanged();
                    }
                } else {
                    getActivity().onBackPressed();
                }
                break;
            case C3033R.id.browse_file_delete_file_btn /* 2131296445 */:
                if (this.isEditMode && !this.isDeleting && !this.isLoading) {
                    List<FileInfo> list6 = this.selectItemList;
                    if (list6 != null && list6.size() > 0) {
                        showDeleteFileNotifyDialog();
                    } else {
                        showShortToast(C3033R.string.select_err);
                    }
                    break;
                }
                break;
            case C3033R.id.browse_file_download_btn /* 2131296446 */:
                if (this.isEditMode && !this.isLoading && !this.isDeleting) {
                    List<FileInfo> list7 = this.selectItemList;
                    if (list7 == null || list7.size() <= 0) {
                        showShortToast(C3033R.string.select_err);
                    } else if (BufChangeHex.readSDCard() <= IConstants.MIN_STORAGE_SPACE) {
                        this.isTaskOpen = false;
                        this.btnBack.performClick();
                        showLongToast(C3033R.string.phone_space_inefficient);
                    }
                    break;
                }
                break;
            case C3033R.id.browse_file_edit_btn /* 2131296447 */:
                this.isEditMode = true;
                this.btnEdit.setVisibility(8);
                this.tvTitle.setVisibility(8);
                this.tvCenter.setVisibility(0);
                this.layoutEditMode.setVisibility(0);
                if (getString(C3033R.string.device_mode_media).equals(this.title)) {
                    this.btnDownLoadFile.setVisibility(0);
                } else {
                    this.btnDownLoadFile.setVisibility(8);
                }
                BrowseFileAdapter browseFileAdapter4 = this.mAdapter;
                if (browseFileAdapter4 != null) {
                    browseFileAdapter4.notifyDataSetChanged();
                }
                break;
        }
    }

    private void updateData(String str) {
        if (TextUtils.isEmpty(str)) {
            return;
        }
        if (str.equals(getString(C3033R.string.local_mode_picture))) {
            this.fileType = 1;
            String photoPath = AppUtils.getPhotoPath(getActivity());
            this.appFilePath = photoPath;
            this.allDataList = AppUtils.getAllLocalFile(photoPath, IConstants.RECORD, false);
            Handler handler = this.mHandler;
            if (handler != null) {
                Message messageObtainMessage = handler.obtainMessage();
                messageObtainMessage.what = IConstants.MSG_UPDATE_UI;
                messageObtainMessage.obj = this.allDataList;
                this.mHandler.sendMessage(messageObtainMessage);
                return;
            }
            return;
        }
        if (str.equals(getString(C3033R.string.local_mode_video))) {
            this.fileType = 2;
            String videoPath = AppUtils.getVideoPath(getActivity());
            this.appFilePath = videoPath;
            this.allDataList = AppUtils.getAllLocalFile(videoPath, IConstants.RECORD, false);
            Handler handler2 = this.mHandler;
            if (handler2 != null) {
                Message messageObtainMessage2 = handler2.obtainMessage();
                messageObtainMessage2.what = IConstants.MSG_UPDATE_UI;
                messageObtainMessage2.obj = this.allDataList;
                this.mHandler.sendMessage(messageObtainMessage2);
            }
        }
    }

    @Override // android.widget.AdapterView.OnItemClickListener
    public void onItemClick(AdapterView<?> adapterView, View view, int i, long j) {
        FileInfo item;
        FileInfo next;
        BrowseFileAdapter browseFileAdapter = this.mAdapter;
        if (browseFileAdapter == null || this.isLoading || this.isDeleting || (item = browseFileAdapter.getItem(i)) == null) {
            return;
        }
        String filename = item.getFilename();
        int fileType = item.getFileType();
        if (TextUtils.isEmpty(filename)) {
            return;
        }
        if (!this.isEditMode) {
            if (fileType == 23133) {
                browseResources(item, item.getPath(), i);
                return;
            }
            return;
        }
        List<FileInfo> list = this.selectItemList;
        if (list != null) {
            if (list.size() > 0) {
                Iterator<FileInfo> it = this.selectItemList.iterator();
                while (true) {
                    if (!it.hasNext()) {
                        next = null;
                        break;
                    }
                    next = it.next();
                    if (next != null && filename.equals(next.getFilename())) {
                        break;
                    }
                }
                if (next == null) {
                    item.setSelected(true);
                    this.selectItemList.add(item);
                } else {
                    item.setSelected(false);
                    this.selectItemList.remove(item);
                    if (this.isAllSelect) {
                        this.isAllSelect = false;
                        this.btnAllSelect.setImageResource(C3033R.drawable.drawable_all_select);
                    }
                }
            } else {
                item.setSelected(true);
                this.selectItemList.add(item);
            }
            if (this.fileInfoList != null) {
                updateCenterTV(this.selectItemList.size(), this.fileInfoList.size());
                if (!this.isAllSelect && this.selectItemList.size() == this.fileInfoList.size()) {
                    this.isAllSelect = true;
                    this.btnAllSelect.setImageResource(C3033R.drawable.drawable_all_select_yellow);
                }
            }
        }
        this.mAdapter.notifyDataSetChanged();
    }

    @Override // com.cooingdv.rcufo.libs.pullrefreshview.layout.BaseFooterView.OnLoadListener
    public void onLoad(BaseFooterView baseFooterView) {
        Handler handler = this.mHandler;
        if (handler != null) {
            handler.postDelayed(this.loadMoreData, 2000L);
        }
    }

    private void initParams() {
        if (this.mBitmapCache == null) {
            this.mBitmapCache = BitmapCache.getInstance();
        }
        if (this.thumbPathMap == null) {
            this.thumbPathMap = new HashMap();
        }
        if (this.durationMap == null) {
            this.durationMap = new HashMap();
        }
        if (this.allDataList == null) {
            this.allDataList = new ArrayList();
        }
        if (this.fileInfoList == null) {
            this.fileInfoList = new ArrayList();
        }
        if (this.selectItemList == null) {
            this.selectItemList = new ArrayList();
        }
        if (TextUtils.isEmpty(this.dFileThumbPath)) {
            this.dFileThumbPath = AppUtils.getThumbPath(getActivity());
        }
        if (this.service == null) {
            this.service = Executors.newSingleThreadExecutor();
        }
        if (this.lastNameList == null) {
            this.lastNameList = new ArrayList();
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void updateCenterTV(int i, int i2) {
        if (i < 0 || i2 < 0 || i2 < i) {
            return;
        }
        String str = String.format(getString(C3033R.string.selected_tip), Integer.valueOf(i), Integer.valueOf(i2));
        TextView textView = this.tvCenter;
        if (textView != null) {
            if (textView.getVisibility() != 0) {
                this.tvCenter.setVisibility(0);
            }
            this.tvCenter.setText(str);
        }
    }

    private void browseResources(FileInfo fileInfo, String str, int i) {
        try {
            if (getActivity() == null || fileInfo == null || TextUtils.isEmpty(str)) {
                return;
            }
            File file = new File(str);
            if (file.exists()) {
                Intent intent = new Intent("android.intent.action.VIEW");
                int iJudgeFileType = AppUtils.judgeFileType(fileInfo.getFilename());
                if (iJudgeFileType == 1) {
                    PhotoViewActivity.goToPhotoView(getActivity(), this.fileInfoList, i);
                    return;
                }
                if (iJudgeFileType == 2) {
                    Intent intent2 = new Intent(getContext(), (Class<?>) VideoViewActivity.class);
                    intent2.putExtra("path", AdPayload.FILE_SCHEME + file.getPath());
                    startActivity(intent2);
                    return;
                }
                showShortToast(getString(C3033R.string.open_file_err));
                if (intent.resolveActivity(getActivity().getPackageManager()) != null) {
                    startActivity(intent);
                    this.mApplication.setIsBrowsing(true);
                }
            }
        } catch (Exception e) {
            Dbug.m13285e(this.TAG, " error  " + e.getMessage());
            e.printStackTrace();
        }
    }

    private void showWaitingDialog(String str) {
        if (getActivity() != null) {
            if (this.waitingDialog == null) {
                WaitingDialog waitingDialog = new WaitingDialog();
                this.waitingDialog = waitingDialog;
                waitingDialog.setCancelable(false);
            }
            if (!TextUtils.isEmpty(str)) {
                this.waitingDialog.setNotifyContent(str);
            }
            if (this.waitingDialog.isShowing()) {
                return;
            }
            Dbug.m13288w("ZZC", "show dialog");
            this.waitingDialog.show(getActivity().getFragmentManager(), "waiting_dialog");
        }
    }

    private void showDeleteFileNotifyDialog() {
        if (getActivity() != null) {
            if (this.deleteNotifyDialog == null) {
                NotifyDialog notifyDialog = new NotifyDialog();
                this.deleteNotifyDialog = notifyDialog;
                notifyDialog.setNotifyDialog(C3033R.string.dialog_tip, C3033R.string.delete_selected_file_tip, C3033R.string.dialog_cancel, C3033R.string.dialog_ok, new NotifyDialog.OnNegativeClickListener() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.4
                    @Override // com.cooingdv.rcufo.dialog.NotifyDialog.OnNegativeClickListener
                    public void onClick() {
                        BrowseFileFragment.this.isTaskOpen = false;
                        BrowseFileFragment.this.deleteNotifyDialog = null;
                    }
                }, new NotifyDialog.OnPositiveClickListener() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.5
                    @Override // com.cooingdv.rcufo.dialog.NotifyDialog.OnPositiveClickListener
                    public void onClick() {
                        BrowseFileFragment.this.isTaskOpen = true;
                        BrowseFileFragment.this.isDeleting = true;
                        BrowseFileFragment.this.dealWithTask(0, false);
                        BrowseFileFragment.this.controlWaitingDeleteDialog(0);
                    }
                });
            }
            if (this.deleteNotifyDialog.isShowing()) {
                return;
            }
            this.deleteNotifyDialog.show(getActivity().getFragmentManager(), "delete_file_notify_dialog");
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void controlWaitingDeleteDialog(int i) {
        WaitingDialog waitingDialog;
        if (getActivity() != null) {
            if (i != 0) {
                if (i == 1 && (waitingDialog = this.waitingDeleteDialog) != null && waitingDialog.isShowing()) {
                    this.waitingDeleteDialog.dismiss();
                    this.waitingDeleteDialog = null;
                    return;
                }
                return;
            }
            if (this.waitingDeleteDialog == null) {
                WaitingDialog waitingDialog2 = new WaitingDialog();
                this.waitingDeleteDialog = waitingDialog2;
                waitingDialog2.setNotifyContent(getString(C3033R.string.deleting_files));
                this.waitingDeleteDialog.setOnWaitingDialog(new WaitingDialog.OnWaitingDialog() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.6
                    @Override // com.cooingdv.rcufo.dialog.WaitingDialog.OnWaitingDialog
                    public void onCancelDialog() {
                        BrowseFileFragment.this.waitingDeleteDialog = null;
                        if (BrowseFileFragment.this.selectItemList != null) {
                            BrowseFileFragment.this.selectItemList.clear();
                        }
                    }
                });
            }
            if (this.waitingDeleteDialog.isShowing()) {
                return;
            }
            this.waitingDeleteDialog.show(getActivity().getFragmentManager(), "waiting_delete_dialog");
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void dealWithTask(final int i, boolean z) {
        Handler handler;
        List<FileInfo> list = this.selectItemList;
        if (list != null) {
            int size = list.size();
            Dbug.m13285e(this.TAG, "dealWithTask is start, isTaskOpen = " + this.isTaskOpen + " , select size = " + size);
            if (this.isTaskOpen) {
                if (z) {
                    if (size > 0) {
                        this.selectItemList.remove(0);
                    }
                    this.failureTimes = 3;
                } else {
                    int i2 = this.failureTimes - 1;
                    this.failureTimes = i2;
                    if (i2 <= 0) {
                        if (size > 0) {
                            this.selectItemList.remove(0);
                        }
                        this.failureTimes = 3;
                    }
                }
                if (this.selectItemList.size() > 0) {
                    final FileInfo fileInfo = this.selectItemList.get(0);
                    if (fileInfo != null) {
                        final String filename = fileInfo.getFilename();
                        if (!TextUtils.isEmpty(filename)) {
                            final int selectPosFromAdapter = getSelectPosFromAdapter(fileInfo);
                            this.mHandler.postDelayed(new Runnable() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.7
                                @Override // java.lang.Runnable
                                public void run() {
                                    if (i == 0) {
                                        String path = fileInfo.getPath();
                                        String str = path.substring(0, path.lastIndexOf("/")) + File.separator + IConstants.SUB_THUMB;
                                        if (BrowseFileFragment.this.fileType == 2) {
                                            String str2 = str + File.separator + BufChangeHex.getVideoThumb(filename, str);
                                            File file = new File(path);
                                            if (file.exists()) {
                                                if (file.delete()) {
                                                    Dbug.m13285e(BrowseFileFragment.this.TAG, " delete video success ! filename -> " + filename);
                                                    if (BrowseFileFragment.this.scanFilesHelper != null) {
                                                        BrowseFileFragment.this.scanFilesHelper.updateToDeleteFile(path);
                                                    }
                                                    File file2 = new File(str2);
                                                    if (file2.exists() && file2.delete()) {
                                                        Dbug.m13285e(BrowseFileFragment.this.TAG, "video thumb success ! thumbPath  = " + str2);
                                                    }
                                                    if (BrowseFileFragment.this.mAdapter != null && selectPosFromAdapter >= 0) {
                                                        FileInfo item = BrowseFileFragment.this.mAdapter.getItem(selectPosFromAdapter);
                                                        if (BrowseFileFragment.this.fileInfoList != null && BrowseFileFragment.this.fileInfoList.remove(item)) {
                                                            BrowseFileFragment.this.mAdapter.remove(item);
                                                        }
                                                    }
                                                    BrowseFileFragment.this.dealWithTask(i, true);
                                                    return;
                                                }
                                                Dbug.m13288w(BrowseFileFragment.this.TAG, "delete video failed ! ");
                                                BrowseFileFragment.this.dealWithTask(i, false);
                                                return;
                                            }
                                            Dbug.m13285e(BrowseFileFragment.this.TAG, "delete video is not exist ! ");
                                            BrowseFileFragment.this.dealWithTask(i, true);
                                            return;
                                        }
                                        String str3 = str + File.separator + BufChangeHex.getVideoThumb(filename, str);
                                        File file3 = new File(path);
                                        if (file3.exists()) {
                                            if (file3.delete()) {
                                                Dbug.m13285e(BrowseFileFragment.this.TAG, "delete image success ! filename -> " + filename);
                                                if (BrowseFileFragment.this.scanFilesHelper != null) {
                                                    BrowseFileFragment.this.scanFilesHelper.updateToDeleteFile(path);
                                                }
                                                File file4 = new File(str3);
                                                if (file4.exists() && file4.delete()) {
                                                    Dbug.m13285e(BrowseFileFragment.this.TAG, "image thumb success ! ");
                                                }
                                                if (BrowseFileFragment.this.mAdapter != null && selectPosFromAdapter >= 0) {
                                                    FileInfo item2 = BrowseFileFragment.this.mAdapter.getItem(selectPosFromAdapter);
                                                    if (BrowseFileFragment.this.fileInfoList != null && BrowseFileFragment.this.fileInfoList.remove(item2)) {
                                                        BrowseFileFragment.this.mAdapter.remove(item2);
                                                    }
                                                }
                                                BrowseFileFragment.this.dealWithTask(i, true);
                                                return;
                                            }
                                            Dbug.m13288w(BrowseFileFragment.this.TAG, "delete image failed ! ");
                                            BrowseFileFragment.this.dealWithTask(i, false);
                                            return;
                                        }
                                        Dbug.m13285e(BrowseFileFragment.this.TAG, "delete image is not exist ! ");
                                        BrowseFileFragment.this.dealWithTask(i, true);
                                    }
                                }
                            }, 300L);
                        } else {
                            dealWithTask(i, false);
                        }
                    }
                    this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.8
                        @Override // java.lang.Runnable
                        public void run() {
                            if (BrowseFileFragment.this.fileInfoList == null || BrowseFileFragment.this.selectItemList == null) {
                                return;
                            }
                            BrowseFileFragment browseFileFragment = BrowseFileFragment.this;
                            browseFileFragment.updateCenterTV(browseFileFragment.selectItemList.size(), BrowseFileFragment.this.fileInfoList.size());
                        }
                    });
                    return;
                }
                Dbug.m13285e(this.TAG, "dealWithTask complete");
                if (i == 0 && (handler = this.mHandler) != null) {
                    handler.postDelayed(this.loadMoreData, 1000L);
                }
                if (this.isEditMode) {
                    this.btnBack.performClick();
                }
            }
        }
    }

    private int getSelectPosFromAdapter(FileInfo fileInfo) {
        if (fileInfo == null || this.mAdapter == null) {
            return -1;
        }
        String filename = fileInfo.getFilename();
        if (TextUtils.isEmpty(filename)) {
            return -1;
        }
        for (int i = 0; i < this.mAdapter.getCount(); i++) {
            FileInfo item = this.mAdapter.getItem(i);
            if (item != null && filename.equals(item.getFilename())) {
                return i;
            }
        }
        return -1;
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void getPictureThumb(final ImageView imageView, final FileInfo fileInfo, String str, String str2) {
        if (imageView == null || fileInfo == null || TextUtils.isEmpty(str)) {
            return;
        }
        final String filename = fileInfo.getFilename();
        final int fileType = fileInfo.getFileType();
        this.future = this.service.submit(new Runnable() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.9
            @Override // java.lang.Runnable
            public void run() {
                int i = fileType;
                if (i != 23132) {
                    if (i != 23133) {
                        return;
                    }
                    final String path = fileInfo.getPath();
                    try {
                        File file = new File(path);
                        if (file.exists()) {
                            BitmapFactory.Options options = new BitmapFactory.Options();
                            options.inJustDecodeBounds = false;
                            options.inSampleSize = 4;
                            final Bitmap bitmapDecodeFile = BitmapFactory.decodeFile(path, options);
                            if (bitmapDecodeFile != null) {
                                BrowseFileFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.9.2
                                    @Override // java.lang.Runnable
                                    public void run() {
                                        if (BrowseFileFragment.this.mBitmapCache != null && BrowseFileFragment.this.thumbPathMap != null) {
                                            BrowseFileFragment.this.thumbPathMap.remove(filename);
                                            BrowseFileFragment.this.thumbPathMap.put(filename, path);
                                            BrowseFileFragment.this.mBitmapCache.addCacheBitmap(bitmapDecodeFile, path);
                                        }
                                        imageView.setImageBitmap(bitmapDecodeFile);
                                    }
                                });
                            } else if (file.delete()) {
                                Dbug.m13285e(BrowseFileFragment.this.TAG, "download image is not opened, so delete this image.");
                            }
                        }
                        return;
                    } catch (Exception e) {
                        Dbug.m13285e(BrowseFileFragment.this.TAG, "err =" + e.getMessage());
                        e.printStackTrace();
                        return;
                    }
                }
                String path2 = fileInfo.getPath();
                try {
                    String strSubstring = path2.substring(0, path2.lastIndexOf("/"));
                    final String str3 = strSubstring + "/" + BufChangeHex.getVideoThumb(filename, strSubstring);
                    File file2 = new File(str3);
                    if (file2.exists()) {
                        BitmapFactory.Options options2 = new BitmapFactory.Options();
                        options2.inJustDecodeBounds = false;
                        options2.inSampleSize = 4;
                        final Bitmap bitmapDecodeFile2 = BitmapFactory.decodeFile(str3, options2);
                        if (bitmapDecodeFile2 != null) {
                            BrowseFileFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.9.1
                                @Override // java.lang.Runnable
                                public void run() {
                                    if (BrowseFileFragment.this.mBitmapCache != null && BrowseFileFragment.this.thumbPathMap != null) {
                                        BrowseFileFragment.this.thumbPathMap.remove(filename);
                                        BrowseFileFragment.this.thumbPathMap.put(filename, str3);
                                        BrowseFileFragment.this.mBitmapCache.addCacheBitmap(bitmapDecodeFile2, str3);
                                    }
                                    imageView.setImageBitmap(bitmapDecodeFile2);
                                }
                            });
                        } else if (file2.delete()) {
                            Dbug.m13285e(BrowseFileFragment.this.TAG, "download image is not opened, so delete this image.");
                        }
                    }
                } catch (Exception e2) {
                    Dbug.m13285e(BrowseFileFragment.this.TAG, "err =" + e2.getMessage());
                    e2.printStackTrace();
                }
            }
        }, filename);
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void getVideoBitmap(ImageView imageView, TextView textView, FileInfo fileInfo, String str, String str2) {
        if (imageView == null || textView == null || fileInfo == null || TextUtils.isEmpty(str)) {
            return;
        }
        String filename = fileInfo.getFilename();
        this.future = this.service.submit(new RunnableC305310(fileInfo.getFileType(), fileInfo, filename, imageView, textView), filename);
    }

    /* JADX INFO: renamed from: com.cooingdv.rcufo.fragment.BrowseFileFragment$10 */
    class RunnableC305310 implements Runnable {
        final /* synthetic */ int val$browseMode;
        final /* synthetic */ FileInfo val$fileInfo;
        final /* synthetic */ ImageView val$imageView;
        final /* synthetic */ String val$name;
        final /* synthetic */ TextView val$textView;

        RunnableC305310(int i, FileInfo fileInfo, String str, ImageView imageView, TextView textView) {
            this.val$browseMode = i;
            this.val$fileInfo = fileInfo;
            this.val$name = str;
            this.val$imageView = imageView;
            this.val$textView = textView;
        }

        @Override // java.lang.Runnable
        public void run() {
            int i = this.val$browseMode;
            if (i != 23132) {
                if (i != 23133) {
                    return;
                }
                try {
                    final String path = this.val$fileInfo.getPath();
                    final String str = (path.contains("/") ? path.substring(0, path.lastIndexOf("/")) : "") + File.separator + IConstants.SUB_THUMB;
                    File file = new File(str);
                    if (!file.exists() && file.mkdir()) {
                        Dbug.m13288w(BrowseFileFragment.this.TAG, " recordThumbPath ok !");
                    }
                    if (new File(path).exists()) {
                        try {
                            final String str2 = str + File.separator + (this.val$name.contains(".") ? BufChangeHex.getVideoThumb(this.val$name, str) : "");
                            File file2 = new File(str2);
                            if (file2.exists()) {
                                BitmapFactory.Options options = new BitmapFactory.Options();
                                options.inJustDecodeBounds = false;
                                options.inSampleSize = 4;
                                final Bitmap bitmapDecodeFile = BitmapFactory.decodeFile(str2, options);
                                if (bitmapDecodeFile != null) {
                                    BrowseFileFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.10.3
                                        @Override // java.lang.Runnable
                                        public void run() {
                                            if (BrowseFileFragment.this.mBitmapCache != null && BrowseFileFragment.this.thumbPathMap != null) {
                                                BrowseFileFragment.this.thumbPathMap.remove(RunnableC305310.this.val$name);
                                                BrowseFileFragment.this.thumbPathMap.put(RunnableC305310.this.val$name, str2);
                                                BrowseFileFragment.this.mBitmapCache.addCacheBitmap(bitmapDecodeFile, str2);
                                            }
                                            RunnableC305310.this.val$imageView.setImageBitmap(bitmapDecodeFile);
                                            if (BrowseFileFragment.this.durationMap != null) {
                                                String videoDuration = BufChangeHex.getVideoDuration(str2);
                                                if (BrowseFileFragment.this.durationMap.get(RunnableC305310.this.val$name) == null) {
                                                    if (videoDuration != null) {
                                                        BrowseFileFragment.this.durationMap.put(RunnableC305310.this.val$name, TimeFormater.getTimeFormatValue(Integer.valueOf(videoDuration).intValue()));
                                                    } else {
                                                        BrowseFileFragment.this.durationMap.put(RunnableC305310.this.val$name, TimeFormater.getTimeFormatValue(0));
                                                    }
                                                }
                                                RunnableC305310.this.val$textView.setText((CharSequence) BrowseFileFragment.this.durationMap.get(RunnableC305310.this.val$name));
                                            }
                                        }
                                    });
                                    return;
                                }
                                if (file2.delete()) {
                                    Dbug.m13288w(BrowseFileFragment.this.TAG, " thumb is null, so delete it!");
                                }
                                final Bitmap bitmapExtractThumbnail = ThumbnailUtils.extractThumbnail(ThumbnailUtils.createVideoThumbnail(path, 1), Sdk.SDKError.Reason.INVALID_BID_PAYLOAD_VALUE, 117);
                                if (bitmapExtractThumbnail != null) {
                                    BrowseFileFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.10.4
                                        @Override // java.lang.Runnable
                                        public void run() {
                                            if (BrowseFileFragment.this.mBitmapCache != null && BrowseFileFragment.this.thumbPathMap != null) {
                                                BrowseFileFragment.this.thumbPathMap.remove(RunnableC305310.this.val$name);
                                                BrowseFileFragment.this.thumbPathMap.put(RunnableC305310.this.val$name, path);
                                                BrowseFileFragment.this.mBitmapCache.addCacheBitmap(bitmapExtractThumbnail, path);
                                            }
                                            RunnableC305310.this.val$imageView.setImageBitmap(bitmapExtractThumbnail);
                                        }
                                    });
                                }
                                Dbug.m13284d(BrowseFileFragment.this.TAG, "the bitmap is null");
                                return;
                            }
                            new Thread(new Runnable() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.10.5
                                @Override // java.lang.Runnable
                                public void run() {
                                    if (AppUtils.getRecordVideoThumb(RunnableC305310.this.val$fileInfo, str + File.separator + RunnableC305310.this.val$name)) {
                                        BrowseFileFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.10.5.1
                                            @Override // java.lang.Runnable
                                            public void run() {
                                                if (BrowseFileFragment.this.mAdapter != null) {
                                                    BrowseFileFragment.this.mAdapter.notifyDataSetChanged();
                                                }
                                            }
                                        });
                                    }
                                }
                            }).start();
                            return;
                        } catch (Exception e) {
                            Dbug.m13285e(BrowseFileFragment.this.TAG, "Exception --> " + e.getMessage());
                            e.printStackTrace();
                            return;
                        }
                    }
                    return;
                } catch (Exception e2) {
                    Dbug.m13285e(BrowseFileFragment.this.TAG, "err =" + e2.getMessage());
                    e2.printStackTrace();
                    return;
                }
            }
            String path2 = this.val$fileInfo.getPath();
            try {
                String strSubstring = path2.substring(0, path2.lastIndexOf("/"));
                final String str3 = strSubstring + "/" + BufChangeHex.getVideoThumb(this.val$name, strSubstring);
                if (new File(str3).exists()) {
                    try {
                        Dbug.m13286i(BrowseFileFragment.this.TAG, " filepath : " + str3);
                        String str4 = strSubstring + File.separator + IConstants.SUB_THUMB;
                        final String str5 = str4 + File.separator + BufChangeHex.getVideoThumb(this.val$name, str4);
                        Dbug.m13288w(BrowseFileFragment.this.TAG, " thumbPath : " + str5);
                        BitmapFactory.Options options2 = new BitmapFactory.Options();
                        options2.inJustDecodeBounds = false;
                        options2.inSampleSize = 4;
                        final Bitmap bitmapDecodeFile2 = BitmapFactory.decodeFile(str5, options2);
                        if (bitmapDecodeFile2 != null) {
                            BrowseFileFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.10.1
                                @Override // java.lang.Runnable
                                public void run() {
                                    if (BrowseFileFragment.this.mBitmapCache != null && BrowseFileFragment.this.thumbPathMap != null) {
                                        BrowseFileFragment.this.thumbPathMap.remove(RunnableC305310.this.val$name);
                                        BrowseFileFragment.this.thumbPathMap.put(RunnableC305310.this.val$name, str5);
                                        BrowseFileFragment.this.mBitmapCache.addCacheBitmap(bitmapDecodeFile2, str5);
                                    }
                                    RunnableC305310.this.val$imageView.setImageBitmap(bitmapDecodeFile2);
                                    if (BrowseFileFragment.this.durationMap != null) {
                                        String videoDuration = BufChangeHex.getVideoDuration(str5);
                                        if (BrowseFileFragment.this.durationMap.get(RunnableC305310.this.val$name) == null) {
                                            if (videoDuration != null) {
                                                BrowseFileFragment.this.durationMap.put(RunnableC305310.this.val$name, TimeFormater.getTimeFormatValue(Integer.valueOf(videoDuration).intValue()));
                                            } else {
                                                BrowseFileFragment.this.durationMap.put(RunnableC305310.this.val$name, TimeFormater.getTimeFormatValue(0));
                                            }
                                        }
                                        RunnableC305310.this.val$textView.setText((CharSequence) BrowseFileFragment.this.durationMap.get(RunnableC305310.this.val$name));
                                    }
                                }
                            });
                            return;
                        }
                        final Bitmap bitmapExtractThumbnail2 = ThumbnailUtils.extractThumbnail(ThumbnailUtils.createVideoThumbnail(str3, 1), Sdk.SDKError.Reason.INVALID_BID_PAYLOAD_VALUE, 117);
                        if (bitmapExtractThumbnail2 != null) {
                            BrowseFileFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.BrowseFileFragment.10.2
                                @Override // java.lang.Runnable
                                public void run() {
                                    if (BrowseFileFragment.this.mBitmapCache != null && BrowseFileFragment.this.thumbPathMap != null) {
                                        BrowseFileFragment.this.thumbPathMap.remove(RunnableC305310.this.val$name);
                                        BrowseFileFragment.this.thumbPathMap.put(RunnableC305310.this.val$name, str3);
                                        BrowseFileFragment.this.mBitmapCache.addCacheBitmap(bitmapExtractThumbnail2, str3);
                                    }
                                    RunnableC305310.this.val$imageView.setImageBitmap(bitmapExtractThumbnail2);
                                    if (BrowseFileFragment.this.durationMap == null || TextUtils.isEmpty((CharSequence) BrowseFileFragment.this.durationMap.get(RunnableC305310.this.val$name))) {
                                        return;
                                    }
                                    RunnableC305310.this.val$textView.setText((CharSequence) BrowseFileFragment.this.durationMap.get(RunnableC305310.this.val$name));
                                }
                            });
                        }
                        Dbug.m13286i(BrowseFileFragment.this.TAG, "the bitmap is null");
                    } catch (Exception e3) {
                        Dbug.m13285e(BrowseFileFragment.this.TAG, "Exception --> " + e3.getMessage());
                        e3.printStackTrace();
                    }
                }
            } catch (Exception e4) {
                Dbug.m13285e(BrowseFileFragment.this.TAG, "err =" + e4.getMessage());
                e4.printStackTrace();
            }
        }
    }

    private class BrowseFileAdapter extends ArrayAdapter<FileInfo> {
        private Context mContext;

        private BrowseFileAdapter(Context context) {
            super(context, 0);
            this.mContext = context;
        }

        @Override // android.widget.ArrayAdapter, android.widget.Adapter
        public View getView(int i, View view, ViewGroup viewGroup) {
            ViewHolder viewHolder;
            if (view == null) {
                view = LayoutInflater.from(this.mContext).inflate(C3033R.layout.item_browse_file, viewGroup, false);
                viewHolder = new ViewHolder();
                viewHolder.bgThumb = (ImageView) view.findViewById(C3033R.id.item_browse_file_thumb);
                viewHolder.icState = (ImageView) view.findViewById(C3033R.id.item_browse_file_select_state);
                viewHolder.bgPicState = (ImageView) view.findViewById(C3033R.id.item_browse_file_picture_state);
                viewHolder.layoutVideo = (RelativeLayout) view.findViewById(C3033R.id.item_browse_file_video_layout);
                viewHolder.tvDuration = (TextView) view.findViewById(C3033R.id.item_browse_file_duration);
                view.setTag(viewHolder);
            } else {
                viewHolder = (ViewHolder) view.getTag();
            }
            FileInfo item = getItem(i);
            if (item != null) {
                if (!item.isDirectory()) {
                    String filename = item.getFilename();
                    if (!TextUtils.isEmpty(filename)) {
                        int iJudgeFileType = AppUtils.judgeFileType(filename);
                        String str = BrowseFileFragment.this.dFileThumbPath + File.separator + filename;
                        if (iJudgeFileType == 1) {
                            viewHolder.layoutVideo.setVisibility(8);
                            viewHolder.bgThumb.setImageResource(C3033R.mipmap.ic_default_image);
                            BrowseFileFragment.this.getPictureThumb(viewHolder.bgThumb, item, str, item.getDateMes());
                            if (checkFileExist(item)) {
                                viewHolder.bgPicState.setVisibility(8);
                            } else {
                                viewHolder.bgPicState.setVisibility(0);
                            }
                        } else if (iJudgeFileType != 2) {
                            viewHolder.bgThumb.setImageResource(C3033R.mipmap.ic_file);
                        } else {
                            viewHolder.bgPicState.setVisibility(8);
                            viewHolder.layoutVideo.setVisibility(0);
                            viewHolder.bgThumb.setImageResource(C3033R.mipmap.ic_default_image);
                            viewHolder.tvDuration.setText(TimeFormater.getTimeFormatValue(0));
                            if (BrowseFileFragment.this.durationMap != null && BrowseFileFragment.this.durationMap.size() > 0 && BrowseFileFragment.this.durationMap.get(filename) != null) {
                                viewHolder.tvDuration.setText((CharSequence) BrowseFileFragment.this.durationMap.get(filename));
                            }
                            BrowseFileFragment.this.getVideoBitmap(viewHolder.bgThumb, viewHolder.tvDuration, item, str, item.getDateMes());
                        }
                        if (!BrowseFileFragment.this.isEditMode) {
                            item.setSelected(false);
                            viewHolder.icState.setVisibility(8);
                        } else {
                            viewHolder.icState.setVisibility(0);
                            if (item.isSelected()) {
                                viewHolder.icState.setImageResource(C3033R.mipmap.ic_selected);
                            } else {
                                viewHolder.icState.setImageResource(C3033R.mipmap.ic_no_select);
                            }
                        }
                    }
                } else {
                    viewHolder.bgThumb.setImageResource(C3033R.mipmap.ic_directory);
                }
            }
            return view;
        }

        private boolean checkFileExist(FileInfo fileInfo) {
            if (fileInfo == null) {
                return false;
            }
            String filename = fileInfo.getFilename();
            int fileType = fileInfo.getFileType();
            if (TextUtils.isEmpty(filename) || fileType != 23133) {
                return false;
            }
            return new File(fileInfo.getPath()).exists();
        }

        private class ViewHolder {
            private ImageView bgPicState;
            private ImageView bgThumb;
            private ImageView icState;
            private RelativeLayout layoutVideo;
            private TextView tvDuration;

            private ViewHolder() {
            }
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public List<FileInfo> selectTypeList(List<FileInfo> list, int i) {
        if (list == null || list.size() == 0) {
            return list;
        }
        ArrayList arrayList = new ArrayList();
        for (FileInfo fileInfo : list) {
            if (fileInfo != null) {
                if (i == 0) {
                    arrayList.add(fileInfo);
                } else if (AppUtils.judgeFileType(fileInfo.getFilename()) == i) {
                    arrayList.add(fileInfo);
                }
            }
        }
        this.isEditMode = false;
        this.isTaskOpen = false;
        List<String> list2 = this.lastNameList;
        if (list2 != null) {
            list2.clear();
        }
        return arrayList;
    }

    private void releaseDialog() {
        this.isLoading = false;
        this.isTaskOpen = false;
        this.isDeleting = false;
        this.isAllSelect = false;
        WaitingDialog waitingDialog = this.waitingDialog;
        if (waitingDialog != null) {
            if (waitingDialog.isShowing()) {
                this.waitingDialog.dismiss();
            }
            this.waitingDialog = null;
        }
        NotifyDialog notifyDialog = this.deleteNotifyDialog;
        if (notifyDialog != null) {
            if (notifyDialog.isShowing()) {
                this.deleteNotifyDialog.dismiss();
            }
            this.deleteNotifyDialog = null;
        }
        WaitingDialog waitingDialog2 = this.waitingDeleteDialog;
        if (waitingDialog2 != null) {
            if (waitingDialog2.isShowing()) {
                this.waitingDeleteDialog.dismiss();
            }
            this.waitingDeleteDialog = null;
        }
        System.gc();
    }

    private void release() {
        this.isEditMode = false;
        Future<String> future = this.future;
        if (future != null) {
            future.cancel(true);
            this.future = null;
        }
        ExecutorService executorService = this.service;
        if (executorService != null) {
            if (!executorService.isShutdown()) {
                this.service.shutdownNow();
            }
            this.service = null;
        }
        Handler handler = this.mHandler;
        if (handler != null) {
            handler.removeCallbacksAndMessages(null);
        }
        ScanFilesHelper scanFilesHelper = this.scanFilesHelper;
        if (scanFilesHelper != null) {
            scanFilesHelper.release();
            this.scanFilesHelper = null;
        }
        releaseDialog();
    }
}
