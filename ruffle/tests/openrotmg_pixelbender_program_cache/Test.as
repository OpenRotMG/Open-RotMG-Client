package {
import flash.display.*;
import flash.filters.ShaderFilter;
import flash.geom.*;
import flash.utils.ByteArray;

public class Test extends MovieClip {
    private function shader():Shader {
        var bytes:ByteArray = new ByteArray();
        var hex:String = "a501000000a405004361636865a1010200000c5f4f7574436f6f726400a3000473726300a1020401000f64737400a10101020008616d6f756e7400a1010800800863686f69636500a1010203000c6f6666736574001d0400c100001000010400c103001000300100f10400100003010080020000001f01004000800000";
        for (var i:int = 0; i < hex.length; i += 2) bytes.writeByte(parseInt(hex.substr(i, 2), 16));
        bytes.position = 0;
        return new Shader(bytes);
    }
    private function job(s:Shader, expected:uint):void {
        var out:BitmapData = new BitmapData(1, 1, true, 0);
        new ShaderJob(s, out).start(true);
        check(out, expected);
    }
    private function filter(s:Shader, src:BitmapData, expected:uint):void {
        var out:BitmapData = new BitmapData(1, 1, true, 0);
        out.applyFilter(src, src.rect, new Point(), new ShaderFilter(s));
        check(out, expected);
    }
    private function check(out:BitmapData, expected:uint):void {
        var actual:uint = out.getPixel32(0, 0);
        if (actual != expected) throw new Error("pixel expected " + expected.toString(16) + " got " + actual.toString(16));
        trace(actual.toString(16));
    }
    public function Test() {
        var a:Shader = shader();
        var b:Shader = shader();
        trace("distinct ShaderData: " + (a.data !== b.data));
        var red:BitmapData = new BitmapData(1, 1, true, 0xffff0000);
        var blue:BitmapData = new BitmapData(1, 1, true, 0xff8000ff);
        a.data.src.input = red;
        a.data.amount.value = [1]; a.data.choice.value = [0]; a.data.offset.value = [0, 0];
        b.data.src.input = blue;
        b.data.amount.value = [0.5]; b.data.choice.value = [1]; b.data.offset.value = [0, 0];
        job(a, 0xffff0000); job(b, 0xff40ffff); job(a, 0xffff0000);
        filter(a, red, 0xffff0000); filter(b, blue, 0xff40ffff); filter(a, red, 0xffff0000);
        a.data.offset.value = [-2, 0];
        job(a, 0xffff0000); filter(a, red, 0); job(a, 0xffff0000);
    }
}
}
