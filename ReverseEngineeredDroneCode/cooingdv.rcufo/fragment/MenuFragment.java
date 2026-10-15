package com.cooingdv.rcufo.fragment;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.RelativeLayout;
import android.widget.TextView;
import androidx.fragment.app.Fragment;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.activity.BrowseFileActivity;
import com.cooingdv.rcufo.activity.GenericActivity;
import com.cooingdv.rcufo.activity.MainActivity;
import com.cooingdv.rcufo.base.BaseFragment;
import com.cooingdv.rcufo.base.MainApplication;
import com.cooingdv.rcufo.dialog.DeclareDialog;
import com.cooingdv.rcufo.socket.SocketClient;
import com.cooingdv.rcufo.tools.IActions;
import com.cooingdv.rcufo.tools.IConstants;
import com.cooingdv.rcufo.tools.PreferencesHelper;
import com.cooingdv.rcufo.utils.Dbug;
import com.unad.sdk.UNADFeedAd;
import com.unad.sdk.UNADFeedAdView;
import com.unad.sdk.dto.AdError;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

/* JADX INFO: loaded from: classes2.dex */
public class MenuFragment extends BaseFragment implements View.OnClickListener {
    private RelativeLayout adLayout;
    private UNADFeedAd mADManager;
    private List<UNADFeedAdView> mAdViewList = new ArrayList();
    private MenuBroadcastReceiver mReceiver;
    private TextView tvVersion;

    private class MenuBroadcastReceiver extends BroadcastReceiver {
        private MenuBroadcastReceiver() {
        }

        @Override // android.content.BroadcastReceiver
        public void onReceive(Context context, Intent intent) {
            if (MenuFragment.this.getActivity() == null || context == null || intent == null) {
                return;
            }
            String action = intent.getAction();
            if (TextUtils.isEmpty(action)) {
                return;
            }
            action.hashCode();
            if (action.equals(IActions.ACTION_SET_FAKE_RESOLUTION)) {
                int fakeResolutionNumber = MainApplication.getInstance().getFakeResolutionNumber();
                MenuFragment.this.tvVersion.setText("Ver:1.9.6." + fakeResolutionNumber);
            }
        }
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.fragment_menu, viewGroup, false);
        ImageView imageView = (ImageView) viewInflate.findViewById(C3033R.id.main_play_btn);
        ImageView imageView2 = (ImageView) viewInflate.findViewById(C3033R.id.main_help_btn);
        ImageView imageView3 = (ImageView) viewInflate.findViewById(C3033R.id.main_setting_btn);
        ImageView imageView4 = (ImageView) viewInflate.findViewById(C3033R.id.main_media_btn);
        this.tvVersion = (TextView) viewInflate.findViewById(C3033R.id.main_version_tv);
        imageView.setOnClickListener(this);
        imageView2.setOnClickListener(this);
        imageView3.setOnClickListener(this);
        imageView4.setOnClickListener(this);
        this.adLayout = (RelativeLayout) viewInflate.findViewById(C3033R.id.main_ad_layout);
        return viewInflate;
    }

    private void initBanner() {
        if (this.mApplication.isFirstStartAPP()) {
            return;
        }
        UNADFeedAd uNADFeedAd = new UNADFeedAd(getActivity(), "Adgo-unit-9273339076", new UNADFeedAd.AdViewListener() { // from class: com.cooingdv.rcufo.fragment.MenuFragment.1
            @Override // com.unad.sdk.UNADFeedAd.AdViewListener
            public void onAdClicked(UNADFeedAdView uNADFeedAdView) {
            }

            @Override // com.unad.sdk.UNADFeedAd.AdViewListener
            public void onAdOpen(UNADFeedAdView uNADFeedAdView) {
            }

            @Override // com.unad.sdk.UNADFeedAd.AdViewListener
            public void onAdLoaded(UNADFeedAdView uNADFeedAdView) {
                MenuFragment.this.mAdViewList.add(uNADFeedAdView);
                MenuFragment.this.adLayout.addView(uNADFeedAdView);
                uNADFeedAdView.render();
            }

            @Override // com.unad.sdk.UNADFeedAd.AdViewListener
            public void onAdFailed(AdError adError) {
                Dbug.m13285e(MenuFragment.this.TAG, "onAdViewFailed.....msg:" + adError.getMessage());
            }

            @Override // com.unad.sdk.UNADFeedAd.AdViewListener
            public void onAdClose(UNADFeedAdView uNADFeedAdView) {
                MenuFragment.this.adLayout.removeView(uNADFeedAdView);
            }
        });
        this.mADManager = uNADFeedAd;
        uNADFeedAd.loadAd();
    }

    @Override // androidx.fragment.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        super.onActivityCreated(bundle);
        if (getActivity() != null) {
            if (!MainApplication.getInstance().isGoogle() && !PreferencesHelper.getSharedPreferences(getActivity().getApplicationContext()).getBoolean(IConstants.DECLARE_AGREE_SHARE_KEY, false)) {
                new DeclareDialog().show(getActivity().getFragmentManager(), "dialog_declare");
                PreferencesHelper.putBooleanValue(getActivity().getApplicationContext(), IConstants.DECLARE_AGREE_SHARE_KEY, true);
            }
            if (this.mReceiver == null) {
                this.mReceiver = new MenuBroadcastReceiver();
            }
            IntentFilter intentFilter = new IntentFilter(IActions.ACTION_SET_FAKE_RESOLUTION);
            if (Build.VERSION.SDK_INT >= 26) {
                getActivity().getApplicationContext().registerReceiver(this.mReceiver, intentFilter, 2);
            } else {
                getActivity().getApplicationContext().registerReceiver(this.mReceiver, intentFilter);
            }
            initBanner();
        }
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public void onResume() {
        super.onResume();
        if (SocketClient.getInstance().isActive()) {
            this.tvVersion.setText("Ver:1.9.6." + MainApplication.getInstance().getFakeResolutionNumber());
        } else {
            this.tvVersion.setText("Ver:1.9.6");
        }
        SocketClient.getInstance().setActivity(getActivity());
        UNADFeedAd uNADFeedAd = this.mADManager;
        if (uNADFeedAd != null) {
            uNADFeedAd.onResume();
        }
    }

    @Override // androidx.fragment.app.Fragment
    public void onPause() {
        super.onPause();
        SocketClient.getInstance().setActivity(null);
        UNADFeedAd uNADFeedAd = this.mADManager;
        if (uNADFeedAd != null) {
            uNADFeedAd.onPause();
        }
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public void onDetach() {
        super.onDetach();
        if (getActivity() != null && this.mReceiver != null) {
            getActivity().getApplicationContext().unregisterReceiver(this.mReceiver);
            this.mReceiver = null;
        }
        List<UNADFeedAdView> list = this.mAdViewList;
        if (list != null) {
            Iterator<UNADFeedAdView> it = list.iterator();
            while (it.hasNext()) {
                it.next().destroy();
            }
        }
        UNADFeedAd uNADFeedAd = this.mADManager;
        if (uNADFeedAd != null) {
            uNADFeedAd.release();
        }
    }

    @Override // android.view.View.OnClickListener
    public void onClick(View view) {
        switch (view.getId()) {
            case C3033R.id.main_help_btn /* 2131296935 */:
                handlerFuncs(IConstants.FRAGMENT_TAG_INSTRUCTIONS);
                break;
            case C3033R.id.main_media_btn /* 2131296936 */:
                Intent intent = new Intent(getActivity(), (Class<?>) BrowseFileActivity.class);
                intent.putExtra(IConstants.KEY_DIR_TYPE, IConstants.VIEW_FRONT);
                startActivity(intent);
                break;
            case C3033R.id.main_play_btn /* 2131296938 */:
                changeDeviceBLFragment();
                break;
            case C3033R.id.main_setting_btn /* 2131296939 */:
                handlerFuncs(IConstants.FRAGMENT_TAG_SETTINGS);
                break;
        }
    }

    private void changeDeviceBLFragment() {
        Fragment deviceBLFragment = (BaseFragment) getActivity().getSupportFragmentManager().findFragmentByTag(IConstants.FRAGMENT_BL_TAG_DEVICE);
        if (deviceBLFragment == null) {
            deviceBLFragment = new DeviceBLFragment();
        }
        ((MainActivity) getActivity()).changeFragment(C3033R.id.main_frame_layout, deviceBLFragment, IConstants.FRAGMENT_BL_TAG_DEVICE, true);
    }

    private void handlerFuncs(String str) {
        if (getActivity() == null || TextUtils.isEmpty(str)) {
            return;
        }
        Intent intent = new Intent(getActivity(), (Class<?>) GenericActivity.class);
        intent.putExtra(IConstants.KEY_FRAGMENT_TAG, str);
        startActivity(intent);
    }
}
