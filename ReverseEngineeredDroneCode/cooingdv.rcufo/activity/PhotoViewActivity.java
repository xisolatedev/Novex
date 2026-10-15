package com.cooingdv.rcufo.activity;

import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Matrix;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.RelativeLayout;
import android.widget.TextView;
import androidx.core.view.OnApplyWindowInsetsListener;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.viewpager.widget.PagerAdapter;
import androidx.viewpager.widget.ViewPager;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.BaseActivity;
import com.cooingdv.rcufo.beans.FileInfo;
import com.cooingdv.rcufo.libs.PhotoViewPager;
import com.cooingdv.rcufo.utils.ImageLoader;
import com.github.chrisbanes.photoview.PhotoView;
import java.io.File;
import java.io.Serializable;
import java.util.List;

/* JADX INFO: loaded from: classes2.dex */
public class PhotoViewActivity extends BaseActivity implements View.OnClickListener {
    private ImageView btnTurnScreen;
    private PhotoViewAdapter mAdapter;
    private ViewPager.OnPageChangeListener mOnPageChangeListener = new ViewPager.OnPageChangeListener() { // from class: com.cooingdv.rcufo.activity.PhotoViewActivity.1
        @Override // androidx.viewpager.widget.ViewPager.OnPageChangeListener
        public void onPageScrollStateChanged(int i) {
        }

        @Override // androidx.viewpager.widget.ViewPager.OnPageChangeListener
        public void onPageScrolled(int i, float f, int i2) {
        }

        @Override // androidx.viewpager.widget.ViewPager.OnPageChangeListener
        public void onPageSelected(int i) {
            if (PhotoViewActivity.this.mAdapter != null) {
                PhotoViewActivity photoViewActivity = PhotoViewActivity.this;
                photoViewActivity.setCounter(i, photoViewActivity.mAdapter.getCount());
                PhotoViewActivity.this.setTitle(PhotoViewActivity.this.mAdapter.getItem(i));
            }
        }
    };
    private PhotoViewPager mViewPager;
    private TextView tvCounter;
    private TextView tvTitle;

    public static void goToPhotoView(Context context, List<FileInfo> list, int i) {
        Intent intent = new Intent(context, (Class<?>) PhotoViewActivity.class);
        Bundle bundle = new Bundle();
        bundle.putSerializable("fileinfo_list", (Serializable) list);
        bundle.putInt("current_position", i);
        intent.putExtras(bundle);
        context.startActivity(intent);
    }

    @Override // com.cooingdv.rcufo.base.BaseActivity, androidx.fragment.app.FragmentActivity, androidx.activity.ComponentActivity, androidx.core.app.ComponentActivity, android.app.Activity
    protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        setContentView(C3033R.layout.activity_photo_view);
        initView();
        Intent intent = getIntent();
        if (intent != null) {
            Bundle extras = intent.getExtras();
            initViewAdapter((List) extras.getSerializable("fileinfo_list"), extras.getInt("current_position", 0));
        } else {
            finish();
        }
    }

    @Override // com.cooingdv.rcufo.base.BaseActivity, androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onDestroy() {
        ImageLoader.getInstance().release();
        super.onDestroy();
    }

    private void initView() {
        RelativeLayout relativeLayout = (RelativeLayout) findViewById(C3033R.id.photo_view_layout);
        ImageView imageView = (ImageView) findViewById(C3033R.id.photo_view_back_btn);
        this.mViewPager = (PhotoViewPager) findViewById(C3033R.id.photo_view_pager);
        this.tvCounter = (TextView) findViewById(C3033R.id.photo_view_counter);
        this.tvTitle = (TextView) findViewById(C3033R.id.photo_view_title);
        this.btnTurnScreen = (ImageView) findViewById(C3033R.id.photo_view_turn_screen_btn);
        imageView.setOnClickListener(this);
        this.btnTurnScreen.setOnClickListener(this);
        this.mViewPager.setPageMargin((int) (getResources().getDisplayMetrics().density * 15.0f));
        this.mViewPager.addOnPageChangeListener(this.mOnPageChangeListener);
        ViewCompat.setOnApplyWindowInsetsListener(relativeLayout, new OnApplyWindowInsetsListener() { // from class: com.cooingdv.rcufo.activity.PhotoViewActivity$$ExternalSyntheticLambda0
            @Override // androidx.core.view.OnApplyWindowInsetsListener
            public final WindowInsetsCompat onApplyWindowInsets(View view, WindowInsetsCompat windowInsetsCompat) {
                return PhotoViewActivity.lambda$initView$0(view, windowInsetsCompat);
            }
        });
    }

    static /* synthetic */ WindowInsetsCompat lambda$initView$0(View view, WindowInsetsCompat windowInsetsCompat) {
        view.setPadding(0, 0, windowInsetsCompat.getInsets(WindowInsetsCompat.Type.navigationBars()).right, 0);
        return windowInsetsCompat;
    }

    private void initViewAdapter(List<FileInfo> list, int i) {
        PhotoViewAdapter photoViewAdapter = new PhotoViewAdapter(getApplicationContext(), list);
        this.mAdapter = photoViewAdapter;
        this.mViewPager.setAdapter(photoViewAdapter);
        if (i < 0 || i >= this.mAdapter.getCount()) {
            return;
        }
        this.mViewPager.setCurrentItem(i);
        setCounter(i, this.mAdapter.getCount());
        String item = this.mAdapter.getItem(i);
        if (TextUtils.isEmpty(item)) {
            return;
        }
        setTitle(item);
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void setCounter(int i, int i2) {
        String string = getString(C3033R.string.counter_format, new Object[]{Integer.valueOf(i + 1), Integer.valueOf(i2)});
        TextView textView = this.tvCounter;
        if (textView != null) {
            textView.setText(string);
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void setTitle(String str) {
        if (TextUtils.isEmpty(str) || this.tvTitle == null) {
            return;
        }
        this.tvTitle.setText(formatTitle(str));
    }

    private String formatTitle(String str) {
        if (TextUtils.isEmpty(str)) {
            return null;
        }
        if (!str.contains(File.separator)) {
            return str;
        }
        String[] strArrSplit = str.split(File.separator);
        return strArrSplit[strArrSplit.length - 1];
    }

    @Override // android.view.View.OnClickListener
    public void onClick(View view) {
        int id = view.getId();
        if (id == C3033R.id.photo_view_back_btn) {
            finish();
        } else {
            if (id != C3033R.id.photo_view_turn_screen_btn) {
                return;
            }
            PhotoViewPager photoViewPager = this.mViewPager;
            PhotoView photoView = (PhotoView) photoViewPager.findViewById(photoViewPager.getCurrentItem());
            photoView.setRotation(photoView.getRotation() == 180.0f ? 0.0f : 180.0f);
        }
    }

    private class PhotoViewAdapter extends PagerAdapter {
        private List<FileInfo> dataList;
        private Context mContext;

        @Override // androidx.viewpager.widget.PagerAdapter
        public boolean isViewFromObject(View view, Object obj) {
            return view == obj;
        }

        public void turnScreen() {
        }

        PhotoViewAdapter(Context context, List<FileInfo> list) {
            this.mContext = context;
            this.dataList = list;
        }

        public String getItem(int i) {
            List<FileInfo> list = this.dataList;
            if (list == null || i >= list.size()) {
                return null;
            }
            return this.dataList.get(i).getPath();
        }

        @Override // androidx.viewpager.widget.PagerAdapter
        public int getCount() {
            List<FileInfo> list = this.dataList;
            if (list == null) {
                return 0;
            }
            return list.size();
        }

        @Override // androidx.viewpager.widget.PagerAdapter
        public Object instantiateItem(ViewGroup viewGroup, int i) {
            PhotoView photoView = new PhotoView(this.mContext);
            String item = getItem(i);
            if (!TextUtils.isEmpty(item)) {
                loadThumbs(photoView, item);
            } else {
                photoView.setImageResource(C3033R.mipmap.ic_default_image);
            }
            viewGroup.addView(photoView);
            photoView.setId(i);
            return photoView;
        }

        @Override // androidx.viewpager.widget.PagerAdapter
        public void destroyItem(ViewGroup viewGroup, int i, Object obj) {
            viewGroup.removeView((View) obj);
        }

        private void loadThumbs(PhotoView photoView, String str) {
            Bitmap bitmapLoadImage = ImageLoader.getInstance().loadImage(this.mContext, str);
            if (bitmapLoadImage.getWidth() > 5000) {
                Matrix matrix = new Matrix();
                matrix.setScale(0.5f, 0.5f);
                bitmapLoadImage = Bitmap.createBitmap(bitmapLoadImage, 0, 0, bitmapLoadImage.getWidth(), bitmapLoadImage.getHeight(), matrix, true);
            }
            photoView.setImageBitmap(bitmapLoadImage);
        }
    }
}
